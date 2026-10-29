/*
 * tests/unit/constants.test.ts: the four lanes are described once each, the 2×2 grid holds each of them once, and a
 * chat starts on a live lane.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_LANE_ID, LANE_BY_ID, LANE_GRID, LANE_IDS, LIVE_LANE_IDS } from "@/lib/constants";

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

  it("starts a new chat on MCP · no auth, the plan's default; both no-auth lanes are live", () => {
    expect(LIVE_LANE_IDS).toEqual(["rest-no-auth", "mcp-no-auth"]);
    expect(DEFAULT_LANE_ID).toBe("mcp-no-auth");
  });

  it("marks each live lane with a step that's already built", () => {
    for (const id of LIVE_LANE_IDS) {
      expect(LANE_BY_ID[id].builtInStep).toBeLessThanOrEqual(4);
    }
  });
});
