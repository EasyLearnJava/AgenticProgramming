/*
 * lib/chat/lane-examples.ts: one forecast call, for the plan's Paris question, as each lane sends it: what the compare
 * view shows. The live lanes' requests are the ones they send: REST · no auth's from the code that builds it, MCP · no
 * auth's as AI SDK's MCP client sends it (MCP 2026-07-28); the auth lanes' are the plan's (PLAN.md 4.3), until they're
 * live.
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
// AI SDK's MCP client, under MCP 2026-07-28: the method and tool in headers, and who's asking in the call's _meta.
const MCP_PROTOCOL_VERSION = "2026-07-28";
const MCP_CLIENT_META = {
  "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
  "io.modelcontextprotocol/clientCapabilities": {},
  "io.modelcontextprotocol/clientInfo": { name: "ai-sdk-mcp-client", version: "1.0.0" },
};

/** An MCP tools/call message, as JSON-RPC text, in the plan's (2025) form. */
function toToolsCallBody(tool: string, input: unknown): string {
  return JSON.stringify({
    jsonrpc: "2.0",
    id: FORECAST_CALL_ID,
    method: "tools/call",
    params: { name: tool, arguments: input },
  });
}

/** A tools/call to our MCP server, as AI SDK's MCP client sends it: its headers and its JSON-RPC text. */
function toOurToolsCall(tool: string, input: unknown): WireRequest {
  return {
    method: "POST",
    url: "https://<this deployment>/api/mcp",
    headers: {
      accept: "application/json, text/event-stream",
      "content-type": "application/json",
      "mcp-method": "tools/call",
      "mcp-name": tool,
      "mcp-protocol-version": MCP_PROTOCOL_VERSION,
    },
    body: JSON.stringify({
      method: "tools/call",
      params: { name: tool, arguments: input, _meta: MCP_CLIENT_META },
      jsonrpc: "2.0",
      id: FORECAST_CALL_ID,
    }),
  };
}

// ③ The forecast call through each lane: within a pair, the same tool and input; only the door changes.
const FORECAST_BY_LANE: Readonly<Record<LaneId, { tool: string; wire: WireRequest }>> = {
  "rest-no-auth": { tool: "get_forecast", wire: toForecastRequest(FORECAST_INPUT, FORECAST_INPUT) },
  "mcp-no-auth": { tool: "get_forecast", wire: toOurToolsCall("get_forecast", FORECAST_INPUT) },
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
