abstract interface class EventConnection {
  Future<void> close();
}

abstract interface class EventConnector {
  Future<EventConnection> connect(String token);
}
