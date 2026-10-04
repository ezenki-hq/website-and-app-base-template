export interface EventConnection {
  close(): Promise<void>;
}

export interface EventConnector {
  connect(token: string): Promise<EventConnection>;
}
