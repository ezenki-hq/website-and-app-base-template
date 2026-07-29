export interface RuntimeConfig {
  apiBaseUrl: string;
  natsWebsocketUrl: string;
}

export const runtimeConfig: RuntimeConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "/api/",
  natsWebsocketUrl: import.meta.env.VITE_NATS_WEBSOCKET_URL || "/nats/",
};
