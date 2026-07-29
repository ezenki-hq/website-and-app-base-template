abstract final class RuntimeConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '/api/',
  );

  static const String natsWebSocketUrl = String.fromEnvironment(
    'NATS_WEBSOCKET_URL',
    defaultValue: '/nats/',
  );
}
