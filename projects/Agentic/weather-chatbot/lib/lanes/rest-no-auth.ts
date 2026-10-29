/*
 * lib/lanes/rest-no-auth.ts: REST · no auth. Our four weather tools run inside /api/chat and call Open-Meteo's APIs
 * themselves, over HTTPS, with no credentials.
 */
import "server-only";
import type { JSONValue, Tool } from "ai";
import type { Lane } from "@/lib/lanes/lane";
import { logError } from "@/lib/logger";
import type { ToolResult } from "@/lib/types";
import { createOpenMeteoClient, type OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import type { WeatherTool } from "@/lib/weather/weather-tool";

const LANE_ID = "rest-no-auth";

type RestNoAuthOptions = { openMeteo?: OpenMeteoClient; now?: () => number };

/** Opens REST · no auth: our four tools, each calling Open-Meteo directly. */
export function openRestNoAuthLane({
  openMeteo = createOpenMeteoClient(),
  now = performance.now.bind(performance),
}: RestNoAuthOptions = {}): Lane {
  // ① Where: api.open-meteo.com (and its geocoding and air-quality hosts), through lib/upstream/open-meteo.ts.
  // ② Auth: none.
  // ③ Tools: our four tool definitions (lib/weather/tools/), as AI SDK tools; toAiTool, below, does ④ and ⑤.
  const tools = {
    geocode_location: toAiTool(OPEN_METEO_TOOLS.geocode_location, openMeteo, now),
    get_current_weather: toAiTool(OPEN_METEO_TOOLS.get_current_weather, openMeteo, now),
    get_forecast: toAiTool(OPEN_METEO_TOOLS.get_forecast, openMeteo, now),
    get_air_quality: toAiTool(OPEN_METEO_TOOLS.get_air_quality, openMeteo, now),
  };
  // ⑥ Clean-up: nothing to close; a REST lane holds no connection.
  return { id: LANE_ID, tools, close: async () => undefined };
}

/**
 * Whether the tool was stopped (Stop, or the answer's end): its signal fired for any reason but the tool's own time
 * budget. A stop isn't a failure to log; Next.js marks a closed browser with its own error, not an AbortError.
 */
function wasStopped(signal: AbortSignal | undefined): boolean {
  if (signal?.aborted !== true) {
    return false;
  }
  const reason: unknown = signal.reason;
  return !(reason instanceof Error && reason.name === "TimeoutError");
}

/** One of our tools as an AI SDK tool: it runs the tool, times it, and records the request for the page. */
function toAiTool<Name extends string, Input, Output extends JSONValue>(
  definition: WeatherTool<Name, Input, Output>,
  openMeteo: OpenMeteoClient,
  now: () => number,
): Tool<Input, ToolResult<Output>> {
  return {
    description: definition.description,
    inputSchema: definition.inputSchema,
    // ④ The call: an HTTPS GET to Open-Meteo, made by the tool itself, with the tool's abort signal (Stop, budget).
    execute: async (input: Input, { abortSignal }: { abortSignal?: AbortSignal }): Promise<ToolResult<Output>> => {
      const startedAt = now();
      try {
        const run = await definition.run(input, { openMeteo, signal: abortSignal });
        // ⑤ The result: Open-Meteo's JSON, already in our names; the page also gets the request and the time.
        return {
          result: run.output,
          summary: definition.summarize(run.output),
          call: { laneId: LANE_ID, wire: run.request, cache: run.cache, durationMs: Math.round(now() - startedAt) },
        };
      } catch (error) {
        // A failure goes to the logs, then on to the model and the chip as our sentence; a stop isn't a failure.
        if (!wasStopped(abortSignal)) {
          logError("tool.failed", error, { tool: definition.name, lane: LANE_ID });
        }
        throw error;
      }
    },
    // The model reads only the weather; the request and the time are for the page.
    toModelOutput: ({ output }: { output: ToolResult<Output> }) => ({ type: "json", value: output.result }),
  };
}
