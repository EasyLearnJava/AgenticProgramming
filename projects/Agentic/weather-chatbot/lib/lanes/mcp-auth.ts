/*
 * lib/lanes/mcp-auth.ts: MCP · with auth. The forecast comes from the same Apify Actor as REST · with auth, run through
 * Apify's MCP server with the same token (lib/upstream/apify-mcp.ts); the Actor can't find places, so geocoding is our
 * MCP server's, as on MCP · no auth. If Apify can't answer, the same forecast comes from MCP · no auth, through our
 * server, and the chip says so (PLAN.md 4.5).
 */
import "server-only";
import type { MCPClientConfig } from "@ai-sdk/mcp";
import {
  ACTOR_TOOL_NAME,
  ANSWER_TIMEOUT_MS,
  APIFY_MCP_ACTOR_BUDGET_MS,
  MCP_CONNECT_TIMEOUT_MS,
  TOOL_TIMEOUT_MS,
} from "@/lib/constants";
import { type Lane, toActorTool } from "@/lib/lanes/lane";
import { callOurMcpTool, connectToOurMcpServer, toMcpTool } from "@/lib/lanes/mcp-no-auth";
import { type Logger, logger } from "@/lib/logger";
import type { McpClient } from "@/lib/types";
import { type ApifyMcpClient, createApifyMcpClient } from "@/lib/upstream/apify-mcp";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";

const LANE_ID = "mcp-auth";
// The no-auth lane behind the same door: where a call goes when Apify can't answer.
const TWIN_LANE_ID = "mcp-no-auth";

type McpAuthOptions = {
  token: string;
  origin: string;
  requestId: string;
  log?: Logger;
  bypassSecret?: string;
  signal?: AbortSignal;
  fetch?: typeof fetch;
  now?: () => number;
  connectTimeoutMs?: number;
  createClient?: (config: MCPClientConfig) => Promise<McpClient>;
  apify?: ApifyMcpClient;
  actorBudgetMs?: number;
};

/** Opens MCP · with auth: our MCP server for geocoding and the fallback; Apify's for the Actor, on its first run. */
export async function openMcpAuthLane({
  token,
  origin,
  requestId,
  log = logger,
  bypassSecret,
  signal,
  fetch: fetchMcp = fetch,
  now = performance.now.bind(performance),
  connectTimeoutMs = MCP_CONNECT_TIMEOUT_MS,
  createClient,
  apify = createApifyMcpClient({ token }),
  actorBudgetMs = APIFY_MCP_ACTOR_BUDGET_MS,
}: McpAuthOptions): Promise<Lane> {
  // ① Where: Apify's MCP server at mcp.apify.com, for the Actor; our own at /api/mcp, for geocoding and the fallback.
  // ② Auth: Authorization: Bearer with APIFY_TOKEN on every request to Apify's server (lib/upstream/apify-mcp.ts);
  // none to ours, which gets the request id and, on a preview, the bypass secret.
  const ours = await connectToOurMcpServer({
    origin,
    requestId,
    log,
    bypassSecret,
    signal,
    fetch: fetchMcp,
    now,
    connectTimeoutMs,
    createClient,
  });
  // ③ Tools: geocoding through our server, as this lane's call; and our copy of Apify's Actor tool, whose run goes
  // through Apify's server: toActorTool() (lib/lanes/lane.ts) does ④ and ⑤, two tools/call messages to Apify
  // (call-actor, with the REST door's limits, then get-dataset-items), and falls back to our server's get_forecast.
  const tools = {
    geocode_location: toMcpTool(OPEN_METEO_TOOLS.geocode_location, ours, now, LANE_ID),
    // The lane opens just before the answer starts, so the answer's budget runs out 50 s from now.
    [ACTOR_TOOL_NAME]: toActorTool({
      laneId: LANE_ID,
      twinLaneId: TWIN_LANE_ID,
      apify,
      runTwin: (input, twinSignal) =>
        callOurMcpTool(OPEN_METEO_TOOLS.get_forecast, ours, input, { laneId: TWIN_LANE_ID, signal: twinSignal, now }),
      requestId,
      log,
      now,
      actorBudgetMs,
      answerDeadline: now() + ANSWER_TIMEOUT_MS,
    }),
  };
  // ⑥ Clean-up: close both connections however the answer ends; Apify's only if a run opened it. The Actor's tool gets
  // 33 s: the run's 20, as on REST · with auth, plus the first handshake's 5, then the fallback's 8.
  return {
    id: LANE_ID,
    tools,
    toolBudgetsMs: { [ACTOR_TOOL_NAME]: actorBudgetMs + TOOL_TIMEOUT_MS },
    close: async () => {
      await Promise.all([ours.close(), apify.close()]);
    },
  };
}
