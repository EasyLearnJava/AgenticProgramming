/*
 * lib/lanes/rest-no-auth.ts: REST · no auth. Our four weather tools run inside /api/chat and call Open-Meteo's APIs
 * themselves, over HTTPS, with no credentials.
 */
import "server-only";
import type { JSONValue, Tool } from "ai";
import { type Lane, toModelWeather } from "@/lib/lanes/lane";
import { type Logger, logger } from "@/lib/logger";
import type { LiveLaneId, ToolResult } from "@/lib/types";
import { createOpenMeteoClient, type OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import type { WeatherTool } from "@/lib/weather/weather-tool";

const LANE_ID = "rest-no-auth";

type RestNoAuthOptions = { log?: Logger; openMeteo?: OpenMeteoClient; now?: () => number };

/** What each of the lane's tools uses: the Open-Meteo client, the request's logger, and a clock for the call's time. */
export type ToolDeps = { openMeteo: OpenMeteoClient; log: Logger; now: () => number };

/** Opens REST · no auth: our four tools, each calling Open-Meteo directly. */
export function openRestNoAuthLane({
  log = logger,
  openMeteo = createOpenMeteoClient(),
  now = performance.now.bind(performance),
}: RestNoAuthOptions = {}): Lane {
  // ① Where: api.open-meteo.com (and its geocoding and air-quality hosts), through lib/upstream/open-meteo.ts.
  // ② Auth: none.
  // ③ Tools: our four tool definitions (lib/weather/tools/), as AI SDK tools; toAiTool, below, does ④ and ⑤.
  const deps: ToolDeps = { openMeteo, log, now };
  const tools = {
    geocode_location: toAiTool(OPEN_METEO_TOOLS.geocode_location, deps, LANE_ID),
    get_current_weather: toAiTool(OPEN_METEO_TOOLS.get_current_weather, deps, LANE_ID),
    get_forecast: toAiTool(OPEN_METEO_TOOLS.get_forecast, deps, LANE_ID),
    get_air_quality: toAiTool(OPEN_METEO_TOOLS.get_air_quality, deps, LANE_ID),
  };
  // ⑥ Clean-up: nothing to close; a REST lane holds no connection.
  return { id: LANE_ID, tools, close: async () => undefined };
}

/**
 * Runs one of our tools once, timed, and records its request for the page as a call through the lane given: this one,
 * or REST · with auth, which calls Open-Meteo for its geocoding, and when it falls back.
 */
export async function runOpenMeteoTool<Name extends string, Input, Output extends JSONValue>(
  definition: WeatherTool<Name, Input, Output>,
  input: Input,
  { openMeteo, log, now }: ToolDeps,
  { laneId, signal }: { laneId: LiveLaneId; signal?: AbortSignal },
): Promise<ToolResult<Output>> {
  const startedAt = now();
  const run = await definition.run(input, { openMeteo, signal, log });
  // ⑤ The result: Open-Meteo's JSON, already in our names; the page also gets the request and the time.
  return {
    result: run.output,
    summary: definition.summarize(run.output),
    call: { laneId, wire: run.request, cache: run.cache, durationMs: Math.round(now() - startedAt) },
  };
}

/**
 * One of our tools as an AI SDK tool for a lane: it runs the tool, times it, and records the request for the page. A
 * failure goes on to the model and the chip as our sentence; the chat logs it, as it does every lane's tool calls.
 */
export function toAiTool<Name extends string, Input, Output extends JSONValue>(
  definition: WeatherTool<Name, Input, Output>,
  deps: ToolDeps,
  laneId: LiveLaneId,
): Tool<Input, ToolResult<Output>> {
  return {
    description: definition.description,
    inputSchema: definition.inputSchema,
    // ④ The call: an HTTPS GET to Open-Meteo, made by the tool itself, with the tool's abort signal (Stop, budget).
    execute: (input: Input, { abortSignal }: { abortSignal?: AbortSignal }): Promise<ToolResult<Output>> =>
      runOpenMeteoTool(definition, input, deps, { laneId, signal: abortSignal }),
    // The model reads only the weather; the request and the time are for the page.
    toModelOutput: toModelWeather,
  };
}
