/*
 * lib/lanes/rest-auth.ts: REST · with auth. The forecast comes from the Open-Meteo Weather Forecast Actor, run through
 * Apify's REST API with our token; the Actor can't find places, so geocoding is Open-Meteo's, as on REST · no auth. If
 * Apify can't answer, the same forecast comes from REST · no auth, and the chip says so (PLAN.md 4.5).
 */
import "server-only";
import { ACTOR_TOOL_NAME, ANSWER_TIMEOUT_MS, AUTH_TOOL_TIMEOUT_MS, TOOL_TIMEOUT_MS } from "@/lib/constants";
import { type Lane, toActorTool } from "@/lib/lanes/lane";
import { runOpenMeteoTool, type ToolDeps, toAiTool } from "@/lib/lanes/rest-no-auth";
import { type Logger, logger } from "@/lib/logger";
import { type ApifyClient, createApifyClient } from "@/lib/upstream/apify";
import { createOpenMeteoClient, type OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";

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
  // ③ Tools: our geocoding, and our copy of Apify's Actor tool; toActorTool() (lib/lanes/lane.ts) does ④ and ⑤, an
  // HTTPS POST to Apify with the Actor's build, time and cost limits in the URL, and falls back to get_forecast.
  const deps: ToolDeps = { openMeteo, log, now };
  const tools = {
    geocode_location: toAiTool(OPEN_METEO_TOOLS.geocode_location, deps, LANE_ID),
    // The lane opens just before the answer starts, so the answer's budget runs out 50 s from now.
    [ACTOR_TOOL_NAME]: toActorTool({
      laneId: LANE_ID,
      twinLaneId: TWIN_LANE_ID,
      apify,
      runTwin: (input, signal) =>
        runOpenMeteoTool(OPEN_METEO_TOOLS.get_forecast, input, deps, { laneId: TWIN_LANE_ID, signal }),
      requestId,
      log,
      now,
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
