abstract interface class NatsConnection {
  Future<void> close();
}

abstract interface class NatsConnector {
  Future<NatsConnection> connect(String token);
}
