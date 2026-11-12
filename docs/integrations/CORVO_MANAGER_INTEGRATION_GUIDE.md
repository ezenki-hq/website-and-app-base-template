# Corvo Manager Integration Guide

This is the integration contract for a Deploy Commander manager that opens a
deployed Corvo proxy. Corvo's installer only handles installation. The deployed
Corvo frontend receives routing interface calls, and the Corvo backend performs
the authorized reconciliation.

The examples target `@ezenki/deploy-commander-installer-interface` `^0.6.3`.
Use an interface library version compatible with the deployed Corvo and Deploy
Commander versions.

```sh
npm install @ezenki/deploy-commander-installer-interface@^0.6.3
```

## Important prerequisite: DNS is separate

Before confirming a route, configure DNS for every selected base domain so it
points at the deployed Corvo proxy. Corvo creates or updates only its local
routing records. It does not call a DNS provider, create DNS records, update
DNS records, or validate public/private DNS resolution. A successful routing
operation therefore does not prove that the hostname is reachable; the caller
or operator must configure and verify DNS separately.

## Responsibility and flow

The calling manager discovers the Corvo manager context, supplies validated
non-secret metadata, opens the Corvo interface, and waits for the child
interface to close. For creation, the backend—not interface metadata—resolves
the sole owned Corvo resource. Corvo obtains the trusted caller identity from
the interface host, obtains a short-lived Corvo manager token, asks the user
for confirmation, and reconciles the complete state through its backend.

```text
caller frontend
  -> wire.startInterface({ manager: corvo.manager, metadata })
  -> deployed Corvo frontend
  -> read-only plan -> user confirmation -> Corvo API
  -> routing snapshot / Envoy
  -> wire.close({ manager: caller, ok, result | error })
```

Opening the interface only starts the read-only planning workflow. A
`create-connection` command creates a Commander connection only after the
user confirms the authoritative plan; `update-routing` and
`delete-connection` retain their existing approval boundaries. None of these
operations makes the upstream network reachable. Arrange workload network
connectivity through the normal Commander workflow, and configure DNS
separately, before treating routing as reachable.

## Discovering Corvo

Use the interface RPC rather than constructing a frontend URL or calling
Commander HTTP endpoints from the caller. Paginate resources and select a
resource whose normalized type is `corvo`. Pass its `manager` field to
`startInterface`; the resource `id` is not a manager ID.

```ts
import { RPC, type RPCCaller } from
  "@ezenki/deploy-commander-installer-interface";

async function listCorvoResources(caller: RPCCaller) {
  const result: RPC.ResourceItem[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await caller.getResources({ type: "corvo", limit: 100, offset });
    result.push(...page.items.filter((item) => item.type.trim().toLowerCase() === "corvo"));
    if (offset + page.items.length >= page.total || page.items.length === 0) return result;
  }
}
```

For `create-connection`, missing or ambiguous Corvo resources are installation
errors (the backend returns `503`); the caller must not guess a resource or
send a `resourceId` in interface metadata. Existing caller-side discovery can
still be used to verify the installation and manager context.

## Commands and metadata

The deployed frontend accepts exactly three commands. Unknown actions and
unknown fields fail closed. `connectionId` is a Commander connection UUID.

### `create-connection`

This command creates a new non-external Commander connection attached to the
sole Corvo resource owned by the configured Corvo manager. Corvo includes the
initial complete routing state in the connection metadata on the Commander
create request. The command deliberately has no `resourceId`, platform
network, connection metadata, or credentials. The backend resolves and
validates exactly one owned resource whose normalized type is `corvo`.

`operationId` is optional. A caller that needs idempotency across reopening the
interface supplies a non-zero UUID and reuses it. If it is omitted, the
frontend generates one before its first plan request and keeps it stable only
while that mounted workflow remains open.

`labels?: {[key: string]: string}` is available only on `create-connection`.
Corvo trims label keys, rejects blank keys and collisions after trimming, and
preserves string values exactly, including `""` and values containing `=`.
Omitting `labels` or passing `{}` requests no labels. Labels appear in the
approval plan and become top-level Commander connection labels; they are not
copied into connection metadata. Supply the same normalized labels when
retrying an operation ID.

Named routing uses the same shape as `update-routing`, without
`connectionId`:

```json
{
  "action": "create-connection",
  "operationId": "22222222-2222-4222-8222-222222222222",
  "labels": { "environment": "production", "release": "v=1" },
  "routing": {
    "example.com": [
      {
        "matchType": "exact",
        "value": "catalog",
        "priority": 100,
        "httpRoutes": [
          {
            "matchType": "prefix",
            "value": "/api",
            "priority": 100,
            "upstream": {
              "name": "catalog",
              "scheme": "http",
              "discoveryType": "static",
              "targets": [{ "host": "catalog", "port": 8080, "weight": 1 }]
            }
          }
        ]
      }
    ]
  }
}
```

The frontend sends normalized labels with both the read-only creation plan
and the confirmed creation request. The plan fingerprint binds the labels and
routing, and the approval view shows the normalized labels before creation.

When the caller intentionally omits a base domain, use the unnamed array
form:

```json
{
  "action": "create-connection",
  "routing": [
    {
      "matchType": "exact",
      "value": "catalog",
      "httpRoutes": [
        {
          "matchType": "prefix",
          "value": "/api",
          "upstream": {
            "name": "catalog",
            "scheme": "http",
            "discoveryType": "static",
            "targets": [{ "host": "catalog", "port": 8080 }]
          }
        }
      ]
    }
  ]
}
```

For unnamed routing, the frontend requires the user to select an existing
local base domain or enter one new valid base-domain name before requesting a
plan. One selected domain applies to the complete array. An empty named
object is invalid. No Commander connection, Corvo routing mutation, or
snapshot activation occurs before the user confirms the plan.

For a shorter caller example, see the
[Corvo Routing Connection Guide](docs/integrations/CORVO_ROUTING_CONNECTION_GUIDE.md).

### `update-routing`

This is a complete desired-state replacement for one Commander connection.
The named-domain form is:

```json
{
  "action": "update-routing",
  "connectionId": "11111111-1111-4111-8111-111111111111",
  "routing": {
    "example.com": [
      {
        "matchType": "exact",
        "value": "catalog",
        "priority": 100,
        "httpRoutes": [
          {
            "matchType": "prefix",
            "value": "/api",
            "priority": 100,
            "upstream": {
              "name": "catalog",
              "scheme": "http",
              "discoveryType": "static",
              "targets": [{ "host": "catalog", "port": 8080, "weight": 1 }]
            }
          }
        ]
      }
    ]
  }
}
```

The `routing` object is keyed by base-domain name. Each value is an array of
host rules. A host rule may contain multiple HTTP routes; every route contains
one upstream; every upstream contains one or more targets. Match types are
`exact`, `prefix`, or `regex_prefix` for host rules. An exact host rule with
`value: ""` matches the base domain itself (such as `example.com`); prefix
and regex-prefix values must be non-empty. Use `exact` or `prefix`
for HTTP routes. HTTP route regex matching is unavailable through this manager
interface release. Schemes are `http` or `https`, and discovery types are
`static` or `dns`.

When the caller intentionally omits a base domain, `routing` is an array:

```json
{
  "action": "update-routing",
  "connectionId": "11111111-1111-4111-8111-111111111111",
  "routing": [
    {
      "matchType": "exact",
      "value": "catalog",
      "httpRoutes": [
        {
          "matchType": "prefix",
          "value": "/api",
          "upstream": {
            "name": "catalog",
            "scheme": "http",
            "discoveryType": "static",
            "targets": [{ "host": "catalog", "port": 8080 }]
          }
        }
      ]
    }
  ]
}
```

The frontend then requires the user to select an existing local base domain or
enter a new valid one. One selected domain applies to the entire array. A
named domain that is absent locally is offered for local `BaseDomain` creation
as part of the confirmed update. Base domains are never linked to or deleted
by a connection.

Host rule `value` may be empty only for `matchType: "exact"`, which matches
the selected bare base domain (for example, `example.com`). Prefix and
regex-prefix host values remain non-empty. HTTP route paths and upstream
strings remain required. Target ports are 1–65535; target weights, when
provided, must be positive integers, and priorities must be non-negative
integers. Omitted weights become `1`; omitted or zero priorities become `100`
during backend normalization. Upstream names, host values, and domains
are trimmed and normalized. Repeated identities with identical definitions are
deduplicated; contradictory duplicates are rejected before any mutation.

### `delete-connection`

```json
{
  "action": "delete-connection",
  "connectionId": "11111111-1111-4111-8111-111111111111"
}
```

Corvo plans and confirms local cleanup, activates the resulting proxy
snapshot, and then asks Commander to delete the real connection. Corvo—not
the calling frontend—performs that Commander deletion.

### Successful creation result and runner use

After confirmation and successful reconciliation, the child interface closes
with the complete `RPC.CreateConnection`-compatible connection result. It is
the result callers use to build a runner `Connection` reference from the
returned resource and connection UUIDs:

```ts
// response is the successful child-close result from requestCorvo below.
const created = response.result as RPC.CreateConnection;
const service = {
  image: "example/catalog:1.0.0",
  connections: [{
    type: "Connection",
    data: {
      resource: created.connection.resource,
      connection: created.connection.id,
    },
  }],
};
```

The runner resolves live platform data from the Corvo resource through the
agent. The connection UUID authorizes the reference because the Corvo resource
is owned by Corvo. Connection metadata stores the `corvo.creation` marker and
`corvo.routing` state; platform data stays on the resource. The returned
connection/config IDs, manager, resource, timestamps, and `external: false`
fields are authoritative.

## Starting the interface

Create one stable wire for the caller's lifetime and reuse it. If the caller
already has a wire, use that instance. The example below is for a caller that
does not answer incoming RPCs. The metadata and caller identity are read by
the deployed Corvo frontend.

```ts
import { createWire, RPC, type Wire, type InterfaceResponse } from
  "@ezenki/deploy-commander-installer-interface";

const wire = createWire(
  async () => ({ ok: false, error: { message: "Unsupported interface request" } }),
);
const caller = RPC.SetupRPCCaller(wire);

async function requestCorvo(wire: Wire, corvo: { manager: string }, metadata: unknown): Promise<InterfaceResponse> {
  const child = await wire.startInterface({ manager: corvo.manager, metadata });
  return child.close;
}
```

Use `caller` with `listCorvoResources`, then pass a selected Corvo resource and
one of the command objects above to `requestCorvo`. Call `wire.end()` when the
caller application is disposed. Check `response.ok` before reading
`response.result`. On `ok: false`, handle `response.error?.message` and optional
`response.error?.status`; cancellation also returns `ok: false`. Use the
library's typed `startInterface` and child-close APIs for your installed
interface version.

## Reconciliation semantics

Every update begins with a read-only plan and requires explicit user
confirmation, including an exact no-op. The backend canonicalizes the whole
desired graph and uses these natural identities:

| Component | Identity |
| --- | --- |
| HostRule | base domain, match type, normalized value |
| HTTPRoute | host rule, match type, normalized value |
| Upstream | normalized name |
| UpstreamTarget | upstream, normalized host, port |

The connection links the complete closure of every declared path: host rules,
HTTP routes, upstreams, and upstream targets. Multiple connections may share
any of those four component types. A host rule can have multiple HTTP routes,
and an upstream can be reused by multiple routes or connections.

Complete-state omission removes only this connection's links. Existing
unlinked routing is never swept. A matching unlinked component is not silently
adopted; the plan shows it as an adoption candidate, and the user must approve
its local component ID. If adoption is declined, the operation does not
proceed.

An exact component already linked elsewhere is reused and shared. If only this
connection links a component, permitted non-identity configuration changes are
updated in place. If another connection links it and the requested
configuration differs, the plan/apply returns `409 Conflict`. Identity changes
create or resolve the new component before removing the old link.

Cleanup is candidate-only and dependency-safe:

- HTTP routes and targets with no remaining connection links may be deleted.
- A host rule is deleted only when it has no connection links and no remaining
  HTTP routes, including unlinked routes.
- An upstream is deleted only when it has no connection links, routes, or
  targets, including unlinked children.
- A base domain is never automatically deleted.

If an unlinked child remains, its parent is retained and only this connection
is unlinked. Routing not linked to the connection is left alone.

Commander metadata is the durable desired-state source. For a fresh creation,
Corvo sends the normalized state under `config.metadata.corvo.routing` in the
initial Commander request, together with the raw `platform_connection` and a
`corvo.creation` recovery marker. For an update, Corvo preserves unrelated
metadata while replacing the routing state:

```json
{
  "unrelated": "preserved",
  "corvo": {
    "otherCorvoData": "preserved",
    "routing": { "version": 1, "baseDomains": { "example.com": [] } }
  }
}
```

The backend reads the latest connection immediately before an update patch.
The routing object is complete state, not a patch; omission removes that
connection's previous routing association. Creation labels travel as the
connection's top-level `labels` field. Corvo records a label digest at
`config.metadata.corvo.creation.labelsHash` to detect changed labels on retry.

## Retry and failure behavior

The frontend generates an operation UUID before apply/delete. Corvo stores the
operation UUID, kind, and confirmed fingerprint. Repeating the same operation
resumes or returns its result; a different operation while one is pending is
`409 Conflict`. A stale plan, changed local graph, missing adoption approval,
shared drift, or uniqueness conflict requires a fresh plan and confirmation.

For `create-connection`, distinct operation UUIDs intentionally create
distinct connections even for the same calling manager and Corvo resource.
Before Commander `POST /connections`, Corvo searches the calling manager's
connections on the resolved resource for the exact non-secret
`corvo.creation.operationId` marker. Zero matches permits one create, one match
recovers that connection, and multiple matches fail closed with `409 Conflict`.
If the caller supplied the UUID, it survives an interface reopen. A UUID
generated by the frontend is stable only for the mounted workflow. If a
Commander response is lost or local reconciliation or snapshot activation
fails, the created connection is retained and the same operation can safely
resume with the same normalized labels. A changed label digest conflicts with
the stored creation marker. A legacy marker-only connection can require one
metadata patch to add its missing routing state. Corvo does not automatically
delete a created connection.

Updates use external-first recovery: Commander metadata is patched, then the
local graph is committed and one post-commit snapshot is activated. If the
local step fails, Commander retains the desired state and Corvo records a safe
failure for retry. On restart, pending updates resume only when the current
Commander routing hash matches the confirmed hash; otherwise they become
conflicted.

Deletion is fail-closed. Local routing cleanup and snapshot activation happen
before Commander `DELETE`. If Commander deletion fails, local routes remain
disabled and the safe `delete_pending` status remains for retry. An
authoritative already-absent Commander response completes the retry.

Successful `update-routing` child results contain `connection_id`,
`operation_id`, `status`, `desired_hash`, `applied_hash`, and `change_counts`.
Successful `delete-connection` child results contain `connection_id`,
`operation_id`, `status: "deleted"`, and `deleted: true`. Successful
`create-connection` instead returns the complete connection DTO described
above so the caller can use its copied platform connection. Errors are safe
structured messages and optional status codes; tokens, passwords, raw
metadata, and secret-bearing connection configuration are never returned.

## Authentication and credentials

The interface frontend obtains metadata with `getMetadata()`, the trusted
parent identity with `getCallingManager()`, and an in-memory Corvo manager
token through the library's `Caller.generateTokenManager()`. It forwards the
calling manager ID as workflow context; it does not accept a caller-supplied
Corvo token.

The backend requires a Commander bearer whose inspected manager ID equals its
configured Commander manager. It separately uses its own Basic credentials to
list and resolve the Corvo resource, list/recover or create a connection, and
GET/PATCH/DELETE an existing referenced connection. It verifies both the
Corvo resource owner and the connection beneficiary manager. A connection
UUID in metadata is a locator, not authority.

The installer captures the approved permanent Commander manager credentials and
injects these Commander variables into the Corvo service environment:

```text
COMMANDER_URL
COMMANDER_MANAGER_ID
COMMANDER_MANAGER_PASSWORD
```

The installer reads this permanent credential from the approved Commander
connection's `config.metadata.username` and `config.metadata.password`; it does
not generate or replace the password. It passes the credential through the
Corvo service environment. The current runner contract can retain service
environment maps in deployment run configuration. The installer does not write
the password to resource or interface metadata, URLs, logs, errors, or Corvo's
database. If the existing Commander connection no longer provides the
credential, reconnect with the same permanent manager password before
continuing. `COMMANDER_URL` alone supports token inspection, but all seven
routing-connection endpoints require the full write configuration. Incomplete
configuration returns `503 Service Unavailable`.

## Backend API

The deployed frontend calls these authenticated Corvo endpoints:

```text
GET  /api/v1/routing-connections/{connectionId}?calling_manager_id={managerId}
POST /api/v1/routing-connections/{connectionId}/routing/plan
PUT  /api/v1/routing-connections/{connectionId}/routing
POST /api/v1/routing-connections/{connectionId}/deletion/plan
POST /api/v1/routing-connections/{connectionId}/deletion
POST /api/v1/routing-connections/creation/plan
POST /api/v1/routing-connections/creation
```

Existing update and delete plan/apply requests include
`calling_manager_id`. Existing update apply includes the normalized complete
state, approved adoption IDs, plan fingerprint, and operation UUID. Delete
includes the plan fingerprint and operation UUID. Creation plan includes
`calling_manager_id`, `operation_id`, normalized complete routing, and optional
`labels`; creation apply repeats those fields and adds approved adoption IDs
and the plan fingerprint. The safe plan response includes normalized labels.
The backend re-resolves the sole Corvo resource and platform connection before
its first Commander mutation, so a stale resource/platform plan stops before
creation.

HTTP mapping is:

| Status | Meaning |
| --- | --- |
| 400 | malformed or contradictory state |
| 401 | missing/invalid Corvo auth or wrong Commander manager |
| 404 | inaccessible/absent connection or beneficiary mismatch |
| 409 | stale plan, adoption, shared drift, uniqueness, pending operation, label mismatch, or ambiguous creation marker |
| 500 | local transaction or snapshot failure |
| 502 | Commander list, resource, connection, or other API failure |
| 503 | incomplete Commander write configuration or missing/ambiguous Corvo resource |

## Caller checklist

1. Select one Corvo resource and use its manager ID.
2. Ensure the workload network is reachable from Corvo.
3. Configure DNS separately; do not treat routing success as reachability.
4. Send either exact named-domain or intentionally unnamed routing metadata.
5. Add optional string labels only to `create-connection` and review them in
   the plan.
6. Reuse one stable interface wire and await the child close result.
7. Let the user review and confirm every plan, including adoption and deletion.
8. Retry the same operation ID and normalized labels after a lost response;
   obtain a new plan after a `409`.
9. Treat safe structured errors and cancellation as normal outcomes.
