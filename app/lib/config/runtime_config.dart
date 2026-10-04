abstract final class RuntimeConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '/api/',
  );

  static const String eventsWebSocketUrl = String.fromEnvironment(
    'EVENTS_WEBSOCKET_URL',
    defaultValue: '/ws/events/',
  );
}
