import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";
import { runtimeConfig } from "./config/runtime";

describe("App", () => {
  it("renders the empty application marker", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Application" })).toBeVisible();
  });
});

describe("runtimeConfig", () => {
  it("uses relative API and Django events WebSocket defaults", () => {
    expect(runtimeConfig).toMatchObject({
      apiBaseUrl: "/api/",
      eventsWebsocketUrl: "/ws/events/",
    });
    expect(runtimeConfig).not.toHaveProperty("natsWebsocketUrl");
  });
});
