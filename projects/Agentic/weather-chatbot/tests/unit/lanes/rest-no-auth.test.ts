/*
 * tests/unit/lanes/rest-no-auth.test.ts: REST · no auth's tools: what a call gives the page, and which failures are
 * logged (a stop isn't, whatever Next.js calls it).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import type { ToolResult } from "@/lib/types";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { createFakeFetch, createMemoryCache, hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

/** Runs the lane's geocoding tool once, for "Paris", with this fetch and signal. */
async function geocodeWith(fetch: typeof globalThis.fetch, abortSignal?: AbortSignal): Promise<ToolResult<unknown>> {
  const openMeteo = createOpenMeteoClient({ fetch, cache: createMemoryCache(), random: () => 0 });
  const tool = openRestNoAuthLane({ openMeteo }).tools.geocode_location;
  if (tool?.execute === undefined) {
    throw new Error("The lane has no geocode_location tool");
  }
  return tool.execute({ query: "Paris" }, { toolCallId: "t1", messages: [], abortSignal, context: {} });
}

/** The events logged so far, read back from the JSON lines. */
function loggedEvents(written: { mock: { calls: unknown[][] } }): unknown[] {
  return written.mock.calls.map((call) => JSON.parse(String(call[0])));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("REST · no auth's tools", () => {
  it("give the weather, a summary, and how the call went: the lane, the request, the cache, the time", async () => {
    const result = await geocodeWith(createFakeFetch([{ fixture: "geocode-paris" }]).fetch);
    expect(result.summary).toBe("Paris, Île-de-France Region, FR · 48.85, 2.35");
    expect(result.call).toMatchObject({
      laneId: "rest-no-auth",
      cache: "miss",
      wire: { method: "GET", headers: { accept: "application/json" } },
    });
    expect(result.call.wire.url).toContain("geocoding-api.open-meteo.com/v1/search?name=Paris");
    expect(result.call.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("log a failure, with the tool and the lane, before it reaches the model", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fail = () => new Response("", { status: 503 });
    await expect(geocodeWith(createFakeFetch([fail, fail]).fetch)).rejects.toBeInstanceOf(UpstreamUnavailableError);
    expect(loggedEvents(written)).toEqual([
      expect.objectContaining({ event: "tool.failed", tool: "geocode_location", lane: "rest-no-auth" }),
    ]);
  });

  it("don't log a stop, even when Next.js names it ResponseAborted rather than AbortError", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const controller = new AbortController();
    const pending = geocodeWith(hangingFetch, controller.signal);
    controller.abort(Object.assign(new Error("The browser closed the connection."), { name: "ResponseAborted" }));
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(written).not.toHaveBeenCalled();
  });

  it("log the tool's own time budget, as a slow answer", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(geocodeWith(hangingFetch, AbortSignal.timeout(20))).rejects.toBeInstanceOf(UpstreamTimeoutError);
    expect(loggedEvents(written)).toEqual([expect.objectContaining({ errorClass: "UpstreamTimeoutError" })]);
  });
});
