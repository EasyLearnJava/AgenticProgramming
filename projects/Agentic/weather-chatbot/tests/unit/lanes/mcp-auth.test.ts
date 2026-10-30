/*
 * tests/unit/lanes/mcp-auth.test.ts: MCP · with auth: geocoding through our MCP server (run in-process), recorded as
 * this lane's call; the forecast through Apify's MCP server (a stand-in, or Apify MCP's real 401 through AI SDK's own
 * client), as our forecast with the token masked; the fallback to MCP · no auth's get_forecast, through our server,
 * with the chip's sentence and one lane.fallback line; and both connections closed.
 */
import { describe, expect, it } from "vitest";
import type { Lane } from "@/lib/lanes/lane";
import { openMcpAuthLane } from "@/lib/lanes/mcp-auth";
import type { ToolResult } from "@/lib/types";
import { type ApifyMcpClient, createApifyMcpClient } from "@/lib/upstream/apify-mcp";
import {
  createApifyMcp401Fetch,
  createApifyMcpStandIn,
  itemsAnswer,
  readActorItems,
  runAnswer,
} from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import type { FakeAnswer } from "@/tests/stubs/open-meteo-stand-ins";

const ACTOR_TOOL = "gochujang--open-meteo-weather-forecast";
const REQUEST_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";
const TOKEN = "test-token-not-real";
// The live check's Dallas question, as the model asked it.
const DALLAS_INPUT = {
  locations: [{ name: "Dallas", latitude: 32.78306, longitude: -96.80667 }],
  forecastDays: 3,
  mode: "daily",
  units: "imperial",
};
const PARIS_INPUT = {
  locations: [{ name: "Paris", latitude: 48.85341, longitude: 2.3488 }],
  forecastDays: 2,
  mode: "hourly",
  units: "metric",
};

/** The lane, with our MCP server in-process (answering from Open-Meteo's recorded answers) and this Apify client. */
async function openWith(apify: ApifyMcpClient, openMeteoAnswers: FakeAnswer[] = []) {
  const { log, lines, events } = createTestLog();
  const ourServer = createMcpServerFetch(openMeteoAnswers);
  const lane = await openMcpAuthLane({
    token: TOKEN,
    origin: TEST_ORIGIN,
    requestId: REQUEST_ID,
    log,
    fetch: ourServer.fetch,
    apify,
  });
  return { lane, lines, events };
}

/** An Apify client whose MCP server is the stand-in, with one run's answers: the run, then the Dallas items. */
function apifyWithOneRun() {
  const server = createApifyMcpStandIn({
    answers: {
      "call-actor": [runAnswer()],
      "get-dataset-items": [itemsAnswer(readActorItems("actor-dallas-daily"))],
    },
  });
  const client = createApifyMcpClient({
    token: TOKEN,
    fetch: (async () => new Response("{}")) as typeof fetch,
    createClient: server.createClient,
  });
  return { client, server };
}

/** Runs one of the lane's tools, as streamText would, with this abort signal. */
async function call(lane: Lane, name: string, input: unknown, abortSignal?: AbortSignal): Promise<ToolResult<unknown>> {
  const tool = lane.tools[name];
  if (tool?.execute === undefined) {
    throw new Error(`The lane has no ${name} tool`);
  }
  return tool.execute(input, { toolCallId: "t1", messages: [], abortSignal, context: {} });
}

describe("openMcpAuthLane", () => {
  it("offers our geocoding and the Actor's tool, which gets 33 s: REST's 28, and the first handshake's 5", async () => {
    const { lane } = await openWith(apifyWithOneRun().client);
    expect(Object.keys(lane.tools).sort()).toEqual(["geocode_location", ACTOR_TOOL]);
    expect(lane.toolBudgetsMs).toEqual({ [ACTOR_TOOL]: 33_000 });
    await lane.close();
  });

  it("geocodes through our MCP server, recorded as this lane's call; Apify isn't asked", async () => {
    const apify = apifyWithOneRun();
    const { lane } = await openWith(apify.client, [{ fixture: "geocode-paris" }]);
    const result = await call(lane, "geocode_location", { query: "Paris" });
    expect(result.call).toMatchObject({ laneId: "mcp-auth", wire: { url: `${TEST_ORIGIN}/api/mcp` } });
    expect(apify.server.connects()).toBe(0);
    await lane.close();
  });

  it("forecasts through Apify's MCP server: the Actor's items, its request with the token masked", async () => {
    const apify = apifyWithOneRun();
    const { lane } = await openWith(apify.client);
    const result = await call(lane, ACTOR_TOOL, DALLAS_INPUT);
    expect(result.result).toMatchObject({ timeZone: "America/Chicago", temperatureUnit: "°F" });
    expect(result.summary).toBe("3 days · 62 to 80 °F · rain up to 45%");
    expect(result.call).toMatchObject({
      laneId: "mcp-auth",
      wire: { url: "https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast" },
    });
    expect(result.call.wire.headers.authorization).toBe("Bearer <APIFY_TOKEN>");
    expect(result.fallback).toBeUndefined();
    // The Actor got its own three fields, with the coordinates rounded and no units, through call-actor, with the REST
    // door's limits.
    expect(apify.server.calls[0]).toEqual({
      name: "call-actor",
      arguments: {
        actor: "gochujang/open-meteo-weather-forecast",
        input: { locations: [{ name: "Dallas", latitude: 32.78, longitude: -96.81 }], forecastDays: 3, mode: "daily" },
        waitSecs: 18,
        callOptions: { build: "1.0.9", timeout: 18, maxTotalChargeUsd: 0.01 },
      },
    });
    await lane.close();
    expect(apify.server.closes()).toBe(1);
  });

  it("falls back to MCP · no auth's get_forecast, through our server, when Apify rejects the token", async () => {
    const apify = createApifyMcp401Fetch();
    const { lane, lines } = await openWith(createApifyMcpClient({ token: TOKEN, fetch: apify.fetch }), [
      { fixture: "forecast-paris" },
    ]);
    const result = await call(lane, ACTOR_TOOL, PARIS_INPUT);
    expect(result.call).toMatchObject({ laneId: "mcp-no-auth", wire: { url: `${TEST_ORIGIN}/api/mcp` } });
    expect(result.result).toMatchObject({ timeZone: "Europe/Paris" });
    expect(result.fallback).toEqual({
      from: "mcp-auth",
      sentence:
        "MCP · with auth is unavailable: Apify didn't accept our token. Answered through MCP · no auth instead. " +
        "(ref b1a0d9e8)",
    });
    expect(lines.filter((line) => line.event === "lane.fallback")).toEqual([
      expect.objectContaining({ level: "error", from: "mcp-auth", to: "mcp-no-auth", errorClass: "AuthError" }),
    ]);
    expect(JSON.stringify([result, lines])).not.toContain(TOKEN);
    await lane.close();
  });
});
