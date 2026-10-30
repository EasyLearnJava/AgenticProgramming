/*
 * lib/lanes/rest-auth.ts: REST · with auth. The forecast comes from the Open-Meteo Weather Forecast Actor, run through
 * Apify's REST API with our token; the Actor can't find places, so geocoding is Open-Meteo's, as on REST · no auth. If
 * Apify can't answer, the same forecast comes from REST · no auth, and the chip says so (PLAN.md 4.5).
 */
import "server-only";
import type { Tool } from "ai";
import {
  ACTOR_TOOL_NAME,
  ANSWER_TIMEOUT_MS,
  AUTH_TOOL_TIMEOUT_MS,
  FALLBACK_MIN_LEFT_MS,
  TOOL_TIMEOUT_MS,
} from "@/lib/constants";
import { ContractError, toAppError } from "@/lib/errors";
import { type Lane, toFallbackSentence, toModelWeather } from "@/lib/lanes/lane";
import { runOpenMeteoTool, type ToolDeps, toAiTool } from "@/lib/lanes/rest-no-auth";
import { type Logger, logFailure, logger } from "@/lib/logger";
import type { ActorForecastInput, Forecast, ForecastInput, ToolResult } from "@/lib/types";
import { type ApifyClient, createApifyClient } from "@/lib/upstream/apify";
import { createOpenMeteoClient, type OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { timeoutSignal } from "@/lib/utils";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import { openMeteoActor } from "@/lib/weather/tools/open-meteo-actor";

const LANE_ID = "rest-auth";
// The no-auth lane behind the same door: where a call goes when Apify can't answer.
const TWIN_LANE_ID = "rest-no-auth";

type RestAuthOptions = {
  token: string;
  requestId: string;
  log?: Logger;
  openMeteo?: OpenMeteoClient;
  apify?: ApifyClient;
  now?: () => number;
  actorBudgetMs?: number;
};

/**
 * What the Actor tool uses besides what every REST tool uses: the Apify client, the request's id, the run's budget, and
 * when the answer's own budget runs out, on the lane's clock.
 */
type ActorDeps = ToolDeps & { apify: ApifyClient; requestId: string; actorBudgetMs: number; answerDeadline: number };

/** Opens REST · with auth: Open-Meteo's geocoding, and our copy of Apify's Actor tool, with its fallback. */
export function openRestAuthLane({
  token,
  requestId,
  log = logger,
  openMeteo = createOpenMeteoClient(),
  apify = createApifyClient({ token }),
  now = performance.now.bind(performance),
  actorBudgetMs = AUTH_TOOL_TIMEOUT_MS,
}: RestAuthOptions): Lane {
  // ① Where: the Actor's run-sync address at api.apify.com, through lib/upstream/apify.ts; geocoding, at Open-Meteo.
  // ② Auth: Authorization: Bearer with APIFY_TOKEN, which lib/upstream/apify.ts puts in the header, never the URL.
  // ③ Tools: our geocoding, and our copy of Apify's Actor tool; toActorTool, below, does ④ and ⑤, and falls back.
  const deps: ToolDeps = { openMeteo, log, now };
  const tools = {
    geocode_location: toAiTool(OPEN_METEO_TOOLS.geocode_location, deps, LANE_ID),
    // The lane opens just before the answer starts, so the answer's budget runs out 50 s from now.
    [ACTOR_TOOL_NAME]: toActorTool({
      ...deps,
      apify,
      requestId,
      actorBudgetMs,
      answerDeadline: now() + ANSWER_TIMEOUT_MS,
    }),
  };
  // ⑥ Clean-up: nothing to close; a REST lane holds no connection. The Actor's tool gets 28 s, not the usual 8: the
  // run's 20, then the fallback's 8.
  return {
    id: LANE_ID,
    tools,
    toolBudgetsMs: { [ACTOR_TOOL_NAME]: actorBudgetMs + TOOL_TIMEOUT_MS },
    close: async () => undefined,
  };
}

/**
 * The Actor tool's input as REST · no auth's get_forecast takes it: the same place, days, hours and units. The input
 * schema holds exactly one location, so a missing one is a bug, never a forecast for 0°, 0°.
 */
function toTwinInput({ locations, forecastDays, mode, units }: ActorForecastInput): ForecastInput {
  const [place] = locations;
  if (place === undefined) {
    throw new ContractError("The Actor tool's input has no location.");
  }
  return {
    latitude: place.latitude,
    longitude: place.longitude,
    days: forecastDays,
    includeHourly: mode === "hourly",
    units,
  };
}

/**
 * Our copy of Apify's Actor tool: it runs the Actor, times it, and records the request. If Apify can't answer (a
 * rejected token, used-up credit, too slow, unreachable, a shape we don't read), the same forecast comes from REST · no
 * auth, marked as a fallback, and the failure is logged once, here, where it's handled. When the tool's own signal has
 * fired (Stop, the answer's budget, the tool's), the answer is ending: the failure is passed on, and nothing falls
 * back. Nor does it with under 12 s of the answer left (PLAN.md 9.3): the call fails with its own sentence instead.
 */
function toActorTool(deps: ActorDeps): Tool<ActorForecastInput, ToolResult<Forecast>> {
  const { apify, requestId, actorBudgetMs, answerDeadline, log, now } = deps;
  return {
    description: openMeteoActor.description,
    inputSchema: openMeteoActor.inputSchema,
    execute: async (input, { abortSignal }) => {
      const startedAt = now();
      try {
        // ④ The call: an HTTPS POST to Apify, with the Actor's input, and its build, time and cost limits in the URL.
        // The run gets the tool's first 20 s: its own timer, joined to the tool's signal.
        const signal = timeoutSignal(actorBudgetMs, abortSignal);
        const run = await openMeteoActor.run(input, { apify, signal, log });
        // ⑤ The result: the Actor's items, as our Forecast (lib/weather/actor-items.ts).
        return {
          result: run.output,
          summary: openMeteoActor.summarize(run.output),
          call: { laneId: LANE_ID, wire: run.request, cache: run.cache, durationMs: Math.round(now() - startedAt) },
        };
      } catch (error) {
        if (abortSignal?.aborted) {
          throw error;
        }
        const failure = toAppError(error);
        if (answerDeadline - now() < FALLBACK_MIN_LEFT_MS) {
          throw failure;
        }
        logFailure(log, "lane.fallback", failure, { from: LANE_ID, to: TWIN_LANE_ID, tool: ACTOR_TOOL_NAME });
        // The twin gets the tool's last 8 s, joined to the same signal, so Stop and the answer's budget still end it.
        const twin = await runOpenMeteoTool(OPEN_METEO_TOOLS.get_forecast, toTwinInput(input), deps, {
          laneId: TWIN_LANE_ID,
          signal: timeoutSignal(TOOL_TIMEOUT_MS, abortSignal),
        });
        return {
          ...twin,
          fallback: { from: LANE_ID, sentence: toFallbackSentence(failure, LANE_ID, TWIN_LANE_ID, requestId) },
        };
      }
    },
    // The model reads only the weather; the request, the time and the fallback are for the page.
    toModelOutput: toModelWeather,
  };
}
