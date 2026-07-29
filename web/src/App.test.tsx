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
  it("uses relative API and NATS defaults", () => {
    expect(runtimeConfig).toMatchObject({
      apiBaseUrl: "/api/",
      natsWebsocketUrl: "/nats/",
    });
  });
});
