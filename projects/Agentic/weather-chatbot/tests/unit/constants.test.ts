/*
 * tests/unit/constants.test.ts: the four lanes are described once each, the 2×2 grid holds each of them once, a chat
 * starts on a live lane, and only the auth lanes need Apify's token.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_LANE_ID, LANE_BY_ID, LANE_GRID, LANE_IDS, LIVE_LANE_IDS, TOKEN_LANE_IDS } from "@/lib/constants";

describe("the lanes", () => {
  it("describes each lane under its own id", () => {
    for (const [id, lane] of Object.entries(LANE_BY_ID)) {
      expect(lane.id).toBe(id);
    }
  });

  it("puts each lane in the 2×2 grid once: REST on the first row, no auth in the first column", () => {
    expect([...LANE_IDS].sort()).toEqual(Object.keys(LANE_BY_ID).sort());
    for (const [rowIndex, row] of LANE_GRID.entries()) {
      expect(row.map((id) => LANE_BY_ID[id].transport)).toEqual(rowIndex === 0 ? ["rest", "rest"] : ["mcp", "mcp"]);
      expect(row.map((id) => LANE_BY_ID[id].auth)).toEqual(["none", "bearer"]);
    }
  });

  it("starts on MCP · no auth, the plan's default; built: both no-auth lanes and REST · with auth", () => {
    expect(LIVE_LANE_IDS).toEqual(["rest-no-auth", "mcp-no-auth", "rest-auth"]);
    expect(DEFAULT_LANE_ID).toBe("mcp-no-auth");
  });

  it("marks each built lane with a step that's already built, and only the auth ones as needing the token", () => {
    for (const id of LIVE_LANE_IDS) {
      expect(LANE_BY_ID[id].builtInStep).toBeLessThanOrEqual(6);
    }
    expect(TOKEN_LANE_IDS.every((id) => LANE_BY_ID[id].auth === "bearer")).toBe(true);
    expect(LIVE_LANE_IDS.filter((id) => LANE_BY_ID[id].auth === "bearer")).toEqual([...TOKEN_LANE_IDS]);
  });
});
