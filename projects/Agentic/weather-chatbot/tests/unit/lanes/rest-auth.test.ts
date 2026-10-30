/*
 * tests/unit/lanes/rest-auth.test.ts: REST · with auth: its two tools, a forecast through the Apify Actor, and every
 * way it falls back to REST · no auth (a rejected token, used-up credit, a shape we don't read, too slow): the same
 * forecast, the chip's sentence, and one lane.fallback line at the failure's level. When the tool's own signal fires
 * (Stop, the answer's budget), nothing falls back, and Stop ends a fallback already running.
 */
import { describe, expect, it } from "vitest";
import { AuthError, UpstreamTimeoutError } from "@/lib/errors";
import type { Lane } from "@/lib/lanes/lane";
import { openRestAuthLane } from "@/lib/lanes/rest-auth";
import type { ToolResult } from "@/lib/types";
import { createApifyClient } from "@/lib/upstream/apify";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { type ApifyAnswer, apifyError, createApifyFetch } from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createFakeFetch, createMemoryCache, type FakeAnswer, hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

const ACTOR_TOOL = "gochujang--open-meteo-weather-forecast";
const REQUEST_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";
const PARIS_INPUT = {
  locations: [{ name: "Paris", latitude: 48.85341, longitude: 2.3488 }],
  forecastDays: 2,
  mode: "hourly",
  units: "metric",
};

/**
 * The lane, with stand-ins for Apify and Open-Meteo, the run's budget and the lane's clock; what each was asked; the
 * lines logged.
 */
function openWith(
  apifyAnswers: ApifyAnswer[] | typeof fetch,
  openMeteoAnswers: FakeAnswer[] | typeof fetch = [],
  actorBudgetMs?: number,
  now?: () => number,
) {
  const apifyFake =
    typeof apifyAnswers === "function" ? { fetch: apifyAnswers, requests: [] } : createApifyFetch(apifyAnswers);
  const openMeteoFake =
    typeof openMeteoAnswers === "function" ? { fetch: openMeteoAnswers, urls: [] } : createFakeFetch(openMeteoAnswers);
  const { log, lines, events } = createTestLog();
  const lane = openRestAuthLane({
    token: "test-token-not-real",
    requestId: REQUEST_ID,
    log,
    actorBudgetMs,
    now,
    apify: createApifyClient({ token: "test-token-not-real", fetch: apifyFake.fetch }),
    openMeteo: createOpenMeteoClient({ fetch: openMeteoFake.fetch, cache: createMemoryCache(), random: () => 0 }),
  });
  return { lane, lines, events, apifyRequests: apifyFake.requests, openMeteoUrls: openMeteoFake.urls };
}

/** Runs one of the lane's tools, as streamText would, with this abort signal. */
async function call(lane: Lane, name: string, input: unknown, abortSignal?: AbortSignal): Promise<ToolResult<unknown>> {
  const tool = lane.tools[name];
  if (tool?.execute === undefined) {
    throw new Error(`The lane has no ${name} tool`);
  }
  return tool.execute(input, { toolCallId: "t1", messages: [], abortSignal, context: {} });
}

describe("openRestAuthLane", () => {
  it("offers our geocoding and the Actor's forecast tool, which gets 28 s: the run's 20, then the fallback's 8", () => {
    const { lane } = openWith([]);
    expect(Object.keys(lane.tools).sort()).toEqual(["geocode_location", ACTOR_TOOL]);
    expect(lane.toolBudgetsMs).toEqual({ [ACTOR_TOOL]: 28_000 });
  });

  it("geocodes with Open-Meteo, as this lane's call", async () => {
    const { lane } = openWith([], [{ fixture: "geocode-paris" }]);
    const result = await call(lane, "geocode_location", { query: "Paris" });
    expect(result.call).toMatchObject({ laneId: "rest-auth", wire: { method: "GET" } });
    expect(result.call.wire.url).toContain("geocoding-api.open-meteo.com");
  });

  it("forecasts through the Actor: its items as our forecast, the token masked, no units sent", async () => {
    const { lane, apifyRequests } = openWith([{ fixture: "actor-paris-assumed", status: 201 }]);
    const result = await call(lane, ACTOR_TOOL, PARIS_INPUT);
    expect(result.result).toMatchObject({ timeZone: "Europe/Paris", temperatureUnit: "°C" });
    expect(result.call).toMatchObject({
      laneId: "rest-auth",
      cache: "miss",
      wire: { method: "POST", headers: { authorization: "Bearer <APIFY_TOKEN>" } },
    });
    expect(result.fallback).toBeUndefined();
    expect(JSON.parse(apifyRequests[0]?.body ?? "{}")).toEqual({
      locations: [{ name: "Paris", latitude: 48.85, longitude: 2.35 }],
      forecastDays: 2,
      mode: "hourly",
    });
  });
});

describe("how REST · with auth falls back to REST · no auth", () => {
  it("a rejected token: REST · no auth's forecast, the chip's sentence with the ref, an error line", async () => {
    const { lane, lines, events } = openWith(
      [{ fixture: "error-401-fake-token", status: 401 }],
      [{ fixture: "forecast-paris" }],
    );
    const result = await call(lane, ACTOR_TOOL, PARIS_INPUT);
    expect(result.call.laneId).toBe("rest-no-auth");
    expect(result.call.wire.url).toContain("api.open-meteo.com/v1/forecast");
    expect(result.result).toMatchObject({ timeZone: "Europe/Paris" });
    expect(result.fallback).toEqual({
      from: "rest-auth",
      sentence:
        "REST · with auth is unavailable: Apify didn't accept our token. Answered through REST · no auth instead. " +
        "(ref b1a0d9e8)",
    });
    expect(events()).toEqual(["info upstream.http", "error lane.fallback", "info upstream.http"]);
    expect(lines[1]).toMatchObject({
      from: "rest-auth",
      to: "rest-no-auth",
      tool: ACTOR_TOOL,
      errorClass: "AuthError",
      message: "Apify answered 401: user-or-token-not-found (User was not found or authentication token is not valid).",
    });
  });

  it("used-up credit: the same fallback, at warn, without a ref", async () => {
    const { lane, events } = openWith(
      [apifyError(402, "x402-payment-required", "Payment required.")],
      [{ fixture: "forecast-paris" }],
    );
    const result = await call(lane, ACTOR_TOOL, PARIS_INPUT);
    expect(result.fallback?.sentence).toBe(
      "REST · with auth is unavailable: Apify's credit for this month is used up. " +
        "Answered through REST · no auth instead.",
    );
    expect(events()).toContain("warn lane.fallback");
  });

  it("an answer in a shape we don't read: the same fallback, logged as a ContractError", async () => {
    const odd = () => new Response(JSON.stringify([{ city: "Paris", temps: [15, 16] }]), { status: 201 });
    const { lane, lines } = openWith([odd], [{ fixture: "forecast-paris" }]);
    const result = await call(lane, ACTOR_TOOL, PARIS_INPUT);
    expect(result.fallback?.sentence).toContain("Apify answered in a way we didn't expect");
    expect(lines.find((line) => line.event === "lane.fallback")).toMatchObject({
      level: "error",
      errorClass: "ContractError",
    });
  });

  it("past the run's own budget: the fallback answers, in the tool's time that's left", async () => {
    const { lane, events } = openWith(hangingFetch, [{ fixture: "forecast-paris" }], 30);
    const result = await call(lane, ACTOR_TOOL, PARIS_INPUT);
    expect(result.call.laneId).toBe("rest-no-auth");
    expect(result.fallback?.sentence).toContain("Apify took too long");
    expect(events()).toEqual(["info upstream.http", "warn lane.fallback", "info upstream.http"]);
  });

  it("Stop during the fallback ends it, after the run's own budget ran out", async () => {
    const controller = new AbortController();
    const { lane } = openWith(hangingFetch, hangingFetch, 30);
    const pending = call(lane, ACTOR_TOOL, PARIS_INPUT, controller.signal);
    setTimeout(() => controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" })), 80);
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
  });

  it("with under 12 s of the answer left, nothing falls back: the call fails with its own sentence", async () => {
    let clock = 0;
    const { lane, events, openMeteoUrls } = openWith(
      [{ fixture: "error-401-fake-token", status: 401 }],
      [],
      undefined,
      () => clock,
    );
    // The lane opened at 0 ms, so the answer's budget runs out at 50,000 ms; the token is refused at 40,000.
    clock = 40_000;
    await expect(call(lane, ACTOR_TOOL, PARIS_INPUT)).rejects.toBeInstanceOf(AuthError);
    expect(events()).toEqual(["info upstream.http"]);
    expect(openMeteoUrls).toEqual([]);
  });

  it("the answer's own budget, firing during the run, isn't Apify being slow: nothing falls back", async () => {
    // The tool's signal fires with a TimeoutError, as AI SDK's does when the answer's 50 s run out.
    const { lane, lines, openMeteoUrls } = openWith(hangingFetch);
    await expect(call(lane, ACTOR_TOOL, PARIS_INPUT, AbortSignal.timeout(30))).rejects.toBeInstanceOf(
      UpstreamTimeoutError,
    );
    expect(lines.map((line) => line.event)).toEqual(["upstream.http"]);
    expect(openMeteoUrls).toEqual([]);
  });

  it("a stop is passed on as it is: no fallback, nothing logged", async () => {
    const { lane, lines, openMeteoUrls } = openWith(hangingFetch);
    const controller = new AbortController();
    const pending = call(lane, ACTOR_TOOL, PARIS_INPUT, controller.signal);
    controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" }));
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(lines).toEqual([]);
    expect(openMeteoUrls).toEqual([]);
  });
});
