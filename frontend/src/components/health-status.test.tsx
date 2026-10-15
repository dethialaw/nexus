import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthStatus } from "./health-status";

function mockFetch(status: number, body: unknown) {
  const fetch = vi.fn(async (request: Request) => {
    expect(new URL(request.url).pathname).toBe("/health");
    return Response.json(body, { status });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HealthStatus", () => {
  it("reports a healthy API", async () => {
    const fetch = mockFetch(200, { status: "ok", database: "ok" });
    render(<HealthStatus />);

    expect(await screen.findByText("API et base de données disponibles")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("reports an unavailable database", async () => {
    const fetch = mockFetch(503, { status: "unavailable", database: "unavailable" });
    render(<HealthStatus />);

    expect(await screen.findByText("API ou base de données indisponible")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("reports an unreachable API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );
    render(<HealthStatus />);

    expect(await screen.findByText("API ou base de données indisponible")).toBeInTheDocument();
  });
});
