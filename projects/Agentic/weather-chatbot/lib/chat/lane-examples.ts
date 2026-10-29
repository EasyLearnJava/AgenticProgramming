/*
 * lib/chat/lane-examples.ts: one forecast call, for the plan's Paris question, as each lane sends it: what the compare
 * view shows. The REST · no auth request comes from the code that sends it; the others are written out as the plan
 * gives them (PLAN.md 4.3), until their lanes are live.
 */
import "server-only";
import { LANE_BY_ID, LANE_IDS } from "@/lib/constants";
import type { CompareCell, ForecastInput, LaneId, WireRequest } from "@/lib/types";
import { toForecastRequest } from "@/lib/upstream/open-meteo";

// ① The call as the model makes it: Paris's coordinates from geocoding, 2 days, hourly, in metric units.
const FORECAST_INPUT: ForecastInput = {
  latitude: 48.85341,
  longitude: 2.3488,
  days: 2,
  includeHourly: true,
  units: "metric",
};
const ACTOR_TOOL = "gochujang--open-meteo-weather-forecast";
const ACTOR_INPUT = {
  locations: [{ name: "Paris", latitude: 48.85341, longitude: 2.3488 }],
  forecastDays: 2,
  mode: "hourly",
};

// ② What the MCP doors add: JSON-RPC over Streamable HTTP; and what the auth lanes add: Apify's token.
const MCP_HEADERS = { "Content-Type": "application/json", Accept: "application/json, text/event-stream" };
const TOKEN_HEADER = { Authorization: "Bearer <APIFY_TOKEN>" };
const FORECAST_CALL_ID = 3;

/** An MCP tools/call message, as JSON-RPC text. */
function toToolsCallBody(tool: string, input: unknown): string {
  return JSON.stringify({
    jsonrpc: "2.0",
    id: FORECAST_CALL_ID,
    method: "tools/call",
    params: { name: tool, arguments: input },
  });
}

// ③ The forecast call through each lane: within a pair, the same tool and input; only the door changes.
const FORECAST_BY_LANE: Readonly<Record<LaneId, { tool: string; wire: WireRequest }>> = {
  "rest-no-auth": { tool: "get_forecast", wire: toForecastRequest(FORECAST_INPUT, FORECAST_INPUT) },
  "mcp-no-auth": {
    tool: "get_forecast",
    wire: {
      method: "POST",
      url: "https://<this deployment>/api/mcp",
      headers: MCP_HEADERS,
      body: toToolsCallBody("get_forecast", FORECAST_INPUT),
    },
  },
  "rest-auth": {
    tool: ACTOR_TOOL,
    wire: {
      method: "POST",
      url: "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items?build=1.0.9&timeout=18&maxTotalChargeUsd=0.01",
      headers: { ...TOKEN_HEADER, "Content-Type": "application/json" },
      body: JSON.stringify(ACTOR_INPUT),
    },
  },
  "mcp-auth": {
    tool: ACTOR_TOOL,
    wire: {
      method: "POST",
      url: "https://mcp.apify.com/?tools=gochujang/open-meteo-weather-forecast",
      headers: { ...TOKEN_HEADER, ...MCP_HEADERS },
      body: toToolsCallBody(ACTOR_TOOL, ACTOR_INPUT),
    },
  },
};

// ④ The compare view's four cells, in the picker's order.
export const COMPARE_CELLS: readonly CompareCell[] = LANE_IDS.map((laneId) => ({
  lane: LANE_BY_ID[laneId],
  ...FORECAST_BY_LANE[laneId],
}));
