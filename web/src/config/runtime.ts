export interface RuntimeConfig {
  apiBaseUrl: string;
  eventsWebsocketUrl: string;
}

export const runtimeConfig: RuntimeConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "/api/",
  eventsWebsocketUrl: import.meta.env.VITE_EVENTS_WEBSOCKET_URL || "/ws/events/",
};
