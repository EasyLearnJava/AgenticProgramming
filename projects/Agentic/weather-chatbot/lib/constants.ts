/*
 * lib/constants.ts: every fixed value the app uses, by name. For now the four lanes; limits and time budgets come with
 * the steps that use them.
 */
import type { LaneId, LaneInfo } from "@/lib/types";

// ① The four lanes: which door, which auth, where the call goes, and the build step that makes each one live.
export const LANE_BY_ID: Readonly<Record<LaneId, LaneInfo>> = {
  "rest-no-auth": {
    id: "rest-no-auth",
    transport: "rest",
    auth: "none",
    label: "REST · no auth",
    door: "api.open-meteo.com",
    builtInStep: 3,
  },
  "rest-auth": {
    id: "rest-auth",
    transport: "rest",
    auth: "bearer",
    label: "REST · with auth",
    door: "api.apify.com",
    builtInStep: 6,
  },
  "mcp-no-auth": {
    id: "mcp-no-auth",
    transport: "mcp",
    auth: "none",
    label: "MCP · no auth",
    door: "/api/mcp, our MCP server",
    builtInStep: 4,
  },
  "mcp-auth": {
    id: "mcp-auth",
    transport: "mcp",
    auth: "bearer",
    label: "MCP · with auth",
    door: "mcp.apify.com",
    builtInStep: 7,
  },
};

// ② The 2×2 picker, row by row: REST, then MCP; without auth, then with it.
export const LANE_GRID: readonly (readonly [LaneId, LaneId])[] = [
  ["rest-no-auth", "rest-auth"],
  ["mcp-no-auth", "mcp-auth"],
];

export const LANE_IDS: readonly LaneId[] = LANE_GRID.flat();

// ③ The lane a new chat starts on (PLAN.md, decision 8).
export const DEFAULT_LANE_ID: LaneId = "mcp-no-auth";
