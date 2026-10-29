/*
 * tests/unit/lanes/rest-no-auth.test.ts: REST · no auth's tools: what a call gives the page, the lane's logger passed
 * on to Open-Meteo's calls, and a failure or a stop passed on as it is (the chat logs a tool's failure, for every lane).
 */
import { describe, expect, it } from "vitest";
import { UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import type { ToolResult } from "@/lib/types";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createFakeFetch, createMemoryCache, hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

/** Runs the lane's geocoding tool once, for "Paris", with this fetch and signal; and the lines the lane logged. */
async function geocodeWith(fetch: typeof globalThis.fetch, abortSignal?: AbortSignal) {
  const openMeteo = createOpenMeteoClient({ fetch, cache: createMemoryCache(), random: () => 0 });
  const { log, lines } = createTestLog();
  const tool = openRestNoAuthLane({ openMeteo, log }).tools.geocode_location;
  if (tool?.execute === undefined) {
    throw new Error("The lane has no geocode_location tool");
  }
  const result: Promise<ToolResult<unknown>> = tool.execute(
    { query: "Paris" },
    { toolCallId: "t1", messages: [], abortSignal, context: {} },
  );
  return { result, lines };
}

describe("REST · no auth's tools", () => {
  it("give the weather, a summary, and how the call went: the lane, the request, the cache, the time", async () => {
    const result = await (await geocodeWith(createFakeFetch([{ fixture: "geocode-paris" }]).fetch)).result;
    expect(result.summary).toBe("Paris, Île-de-France Region, FR · 48.85, 2.35");
    expect(result.call).toMatchObject({
      laneId: "rest-no-auth",
      cache: "miss",
      wire: { method: "GET", headers: { accept: "application/json" } },
    });
    expect(result.call.wire.url).toContain("geocoding-api.open-meteo.com/v1/search?name=Paris");
    expect(result.call.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("pass the lane's logger on to Open-Meteo's calls, so their lines carry the lane's fields", async () => {
    const { result, lines } = await geocodeWith(createFakeFetch([{ fixture: "geocode-paris" }]).fetch);
    await result;
    expect(lines).toEqual([
      expect.objectContaining({ event: "upstream.http", host: "geocoding-api.open-meteo.com", status: "ok" }),
    ]);
  });

  it("pass a failure on as our class, and a stop as it is, whatever Next.js calls it", async () => {
    const fail = () => new Response("", { status: 503 });
    await expect((await geocodeWith(createFakeFetch([fail, fail]).fetch)).result).rejects.toBeInstanceOf(
      UpstreamUnavailableError,
    );
    await expect((await geocodeWith(hangingFetch, AbortSignal.timeout(20))).result).rejects.toBeInstanceOf(
      UpstreamTimeoutError,
    );
    const controller = new AbortController();
    const { result, lines } = await geocodeWith(hangingFetch, controller.signal);
    controller.abort(Object.assign(new Error("The browser closed the connection."), { name: "ResponseAborted" }));
    await expect(result).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(lines).toEqual([]);
  });
});
