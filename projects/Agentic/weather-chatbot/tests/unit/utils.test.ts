/*
 * tests/unit/utils.test.ts: every helper in lib/utils.ts.
 */
import { describe, expect, it } from "vitest";
import { toHost, toWireText } from "@/lib/utils";

describe("toWireText", () => {
  it("writes a request without a body as its request line and headers", () => {
    expect(toWireText({ method: "GET", url: "https://example.com/a?b=1", headers: {} })).toBe(
      "GET https://example.com/a?b=1",
    );
  });

  it("writes headers one per line, then a blank line and the body", () => {
    const text = toWireText({
      method: "POST",
      url: "https://example.com/run",
      headers: { Authorization: "Bearer <TOKEN>", "Content-Type": "application/json" },
      body: '{"a":1}',
    });
    expect(text).toBe(
      'POST https://example.com/run\nAuthorization: Bearer <TOKEN>\nContent-Type: application/json\n\n{"a":1}',
    );
  });
});

describe("toHost", () => {
  it("takes the host from a URL, with or without a path or query", () => {
    expect(toHost("https://api.apify.com/v2/acts/x/run-sync-get-dataset-items?timeout=18")).toBe("api.apify.com");
    expect(toHost("https://mcp.apify.com/?tools=gochujang/open-meteo-weather-forecast")).toBe("mcp.apify.com");
    expect(toHost("https://geocoding-api.open-meteo.com")).toBe("geocoding-api.open-meteo.com");
  });

  it("keeps a placeholder host as it's written", () => {
    expect(toHost("https://<this deployment>/api/mcp")).toBe("<this deployment>");
  });
});
