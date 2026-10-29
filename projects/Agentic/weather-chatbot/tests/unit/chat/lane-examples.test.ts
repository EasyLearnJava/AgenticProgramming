/*
 * tests/unit/chat/lane-examples.test.ts: the compare view's examples keep the plan's rules: within a pair, the same
 * tool with the same input, only the door changing; a token to Apify and to no other host.
 */
import { describe, expect, it } from "vitest";
import { COMPARE_CELLS } from "@/lib/chat/lane-examples";
import { LANE_IDS } from "@/lib/constants";
import type { CompareCell, LaneId } from "@/lib/types";
import { toForecastRequest } from "@/lib/upstream/open-meteo";
import { toHost } from "@/lib/utils";

const APIFY_HOSTS = ["api.apify.com", "mcp.apify.com"];

/** The example for one lane. */
function cellFor(laneId: LaneId): CompareCell {
  const cell = COMPARE_CELLS.find((each) => each.lane.id === laneId);
  if (cell === undefined) {
    throw new Error(`No example for ${laneId}`);
  }
  return cell;
}

/** The arguments inside an MCP door's tools/call message. */
function toolsCallArguments(cell: CompareCell): unknown {
  return JSON.parse(cell.wire.body ?? "{}").params.arguments;
}

describe("the lane examples", () => {
  it("shows the four lanes, in the picker's order", () => {
    expect(COMPARE_CELLS.map((cell) => cell.lane.id)).toEqual([...LANE_IDS]);
  });

  it("sends the no-auth pair's arguments, through the REST door, as the very request REST · no auth shows", () => {
    const mcp = cellFor("mcp-no-auth");
    const input = toolsCallArguments(mcp) as Parameters<typeof toForecastRequest>[0] &
      Parameters<typeof toForecastRequest>[1];
    expect(mcp.tool).toBe(cellFor("rest-no-auth").tool);
    expect(toForecastRequest(input, input)).toEqual(cellFor("rest-no-auth").wire);
  });

  it("sends the auth pair the same tool, with the same Actor input", () => {
    expect(cellFor("rest-auth").tool).toBe(cellFor("mcp-auth").tool);
    expect(JSON.parse(cellFor("rest-auth").wire.body ?? "")).toEqual(toolsCallArguments(cellFor("mcp-auth")));
  });

  it("puts a token on every request to Apify, and on no other request", () => {
    for (const { wire } of COMPARE_CELLS) {
      expect(wire.headers.Authorization !== undefined, wire.url).toBe(APIFY_HOSTS.includes(toHost(wire.url)));
    }
  });
});
