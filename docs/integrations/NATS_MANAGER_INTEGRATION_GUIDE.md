# NATS Manager Integration Guide

This guide is for developers connecting another Deploy Commander manager or application to a NATS server managed by this project. It covers requesting a NATS user, handling approval, and supplying the resulting credentials to a deployment. The manager owns the NATS resource and provisions a distinct NATS user for each Deploy Commander connection.

For general manager startup, authentication, and interface RPC, see the [Manager Interface Guide](docs/integrations/MANAGER_INTERFACE_GUIDE.md). For the broader resource connection lifecycle, see the [Resource Connection Manager Guide](docs/integrations/RESOURCE_CONNECTION_MANAGER_GUIDE.md). For runner service plans and connection references, see the [Deployment Runner Implementation Guide](docs/integrations/DEPLOYMENT_RUNNER_IMPLEMENTATION_GUIDE.md).

## Discover the resource and its inputs

Select a resource whose `resource_type` is `nats`, and use its `connectionInputs` metadata to present the fields supported by that resource. The current contract is version 3. It defines these inputs:

| Field | Required | Meaning |
| --- | --- | --- |
| `requestedAccessLevel` | Yes | One of the access levels below. |
| `userName` | Yes | NATS user name, 1–64 characters, starting with a letter or digit and containing only letters, digits, `_`, or `-`. |
| `publishAllow` | Custom access only | NATS subject patterns the user may publish to. |
| `publishDeny` | Custom access only | NATS subject patterns the user may not publish to. |
| `subscribeAllow` | Custom access only | NATS subject patterns the user may subscribe to. |
| `subscribeDeny` | Custom access only | NATS subject patterns the user may not subscribe to. |

Access levels are:

| Level | Effective access |
| --- | --- |
| `subscribe` | Subscribe to all subjects in the shared `DC_APP` account; publishing is denied. |
| `publish` | Publish to all subjects in `DC_APP`; subscribing is denied. |
| `messaging` | Publish and subscribe in `DC_APP`; JetStream management requests are denied. |
| `account_full` | Unrestricted access to `DC_APP`, including its JetStream API. |
| `custom` | Apply the requested publish and subscribe subject lists. |
| `system` | Full access to NATS system-account operations. It does not grant access to private `DC_APP` subjects. |

For `custom`, an empty allow list means all subjects in that direction, subject to the deny list. An empty deny list denies none. Subject patterns use NATS tokens such as `orders.*` and `orders.>`; whitespace, empty tokens, and a `>` token anywhere except the end are rejected. Permission lists are not accepted for other access levels. Do not send the retired `tenantAccount` field.

## Request a connection

Start the selected resource manager interface using the documented Deploy Commander interface workflow. The trusted calling manager identity and opened resource context come from Deploy Commander; do not put a caller-supplied manager ID in the request or treat one as authorization. For Custom Deployer's group workflow, the resource-owning manager receives an opening request like:

```json
{
  "action": "create-connection",
  "resource": "<nats-resource-uuid>",
  "connectionInput": {
    "userName": "orders-worker",
    "requestedAccessLevel": "custom",
    "publishAllow": ["orders.created"],
    "publishDeny": [],
    "subscribeAllow": ["orders.>"],
    "subscribeDeny": ["orders.private.>"]
  },
  "labels": {
    "custom_deployer_group_id": "<deployment-group-uuid>",
    "custom_deployer_connection_origin": "created"
  }
}
```

`connectionInput` may be omitted in the group workflow. If `userName` or `requestedAccessLevel` was not supplied, the approval view asks the user to choose it. A supplied value stays fixed during approval. The approval view shows the effective permissions; only the four permission lists can be supplied with a `custom` selection. Check the returned interface response: `ok: false` carries an error and means the request failed or was denied.

For a successful create, the response contains the created connection's identity:

```json
{
  "manager": "<nats-manager-uuid>",
  "ok": true,
  "result": {
    "connection": {
      "id": "<connection-uuid>",
      "resource": "<nats-resource-uuid>",
      "labels": {
        "custom_deployer_group_id": "<deployment-group-uuid>",
        "custom_deployer_connection_origin": "created"
      }
    }
  }
}
```

Use the connection ID and resource ID for subsequent connection references. The interface result contains no credentials. Do not expect a NATS JWT, NKey seed, or `.creds` text in the response, resource metadata, connection metadata, labels, or logs.

## Use the connection in a deployment

Use the authorized Deploy Commander connection secret reference wherever the runner accepts a secret binding:

```text
[[secret:connection:<connection-uuid>:NATS_CREDS]]
```

For example, provide it as an environment value in the manager's runner plan:

```json
{
  "environment": {
    "NATS_CREDS": "[[secret:connection:<connection-uuid>:NATS_CREDS]]"
  }
}
```

Have the NATS client load that `.creds` content using its supported credentials-file option. Keep the reference in the runner plan; never resolve the secret in browser code or copy its value into ordinary configuration. The runner obtains secret values through Deploy Commander's authorized secret handling.

When a service consumes the NATS resource through a connection, include both IDs in the runner connection reference:

```json
{
  "type": "Connection",
  "data": {
    "resource": "<nats-resource-uuid>",
    "connection": "<connection-uuid>"
  }
}
```

The resource ID is required so the runner can resolve the live connection descriptor. Use the secret binding for `NATS_CREDS`; the connection reference identifies and authorizes the resource connection.

## Link, unlink, and delete connections

Custom Deployer uses the resource manager for connection lifecycle actions. Linking an existing visible connection labels it as `imported`; unlinking removes group labels while preserving the Deploy Commander connection and its NATS user. Connections created for the group are marked `created`; deleting one revokes its NATS user before Deploy Commander removes the connection and its owned secret. Do not revoke imported connections when unlinking them.

For a created group connection, Custom Deployer sends the connection IDs in an array, including for a single connection:

```json
{
  "action": "delete-connection",
  "connections": ["<connection-uuid>"]
}
```

The manager validates resource ownership and connection identity before revocation. A failed deletion can be retried safely; wait for the workflow response and report failure to the caller rather than deleting the Deploy Commander record yourself. A retry of a create request is accepted only when its prior request matches the same access settings and group labels.

## Security and operational boundaries

- The NATS server and its long-running service do not mount signing keys. Only one-shot setup and connection jobs mount the private signing material.
- Account and user changes run through one-shot jobs and do not restart NATS.
- The first ordinary connection records provenance for the shared `DC_APP` account. If an unmarked account with that name already exists, ordinary connection creation fails closed; resolve the collision rather than replacing the account.
- `system` access is for NATS system operations and is separate from application-account access. Choose the narrowest access level that supports the workload.
- Deploy Commander owns the connection's `NATS_CREDS` secret. Deleting a created connection revokes its NATS identity and removes that owned secret through the normal lifecycle.

For setup, backup, recovery, and current limitations, see the [project README](README.md).
