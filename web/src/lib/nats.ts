export interface NatsConnection {
  close(): Promise<void>;
}

export interface NatsConnector {
  connect(token: string): Promise<NatsConnection>;
}
