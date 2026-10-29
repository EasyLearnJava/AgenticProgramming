/*
 * tests/unit/chat/sample-conversation.test.ts: the sample keeps the plan's rule: within a pair the destination, the tool
 * and its input stay the same and only the door changes; a token goes to Apify and nowhere else.
 */
import { describe, expect, it } from "vitest";
import { SAMPLE_COMPARE_CELLS, SAMPLE_MESSAGES_BY_LANE } from "@/lib/chat/sample-conversation";
import { LANE_IDS } from "@/lib/constants";
import type { LaneId, ToolCallView, WireRequest } from "@/lib/types";
import { toHost } from "@/lib/utils";

const APIFY_HOSTS = ["api.apify.com", "mcp.apify.com"];

/** Every tool call in the sample, on one lane. */
function callsFor(laneId: LaneId): ToolCallView[] {
  return SAMPLE_MESSAGES_BY_LANE[laneId].flatMap((message) => message.toolCalls ?? []);
}

/** The sample's forecast call, as it goes through one lane. */
function forecastCallFor(laneId: LaneId): ToolCallView | undefined {
  return callsFor(laneId).find((call) => call.id === "forecast");
}

describe("the sample conversation", () => {
  it("has the question and the answer on every lane, each call marked with that lane", () => {
    for (const laneId of LANE_IDS) {
      expect(SAMPLE_MESSAGES_BY_LANE[laneId].map((message) => message.role)).toEqual(["user", "bot"]);
      for (const call of callsFor(laneId)) {
        expect(call.laneId).toBe(laneId);
      }
    }
  });

  it("sends the same tool with the same input through both doors of a pair", () => {
    for (const [rest, mcp] of [
      ["rest-no-auth", "mcp-no-auth"],
      ["rest-auth", "mcp-auth"],
    ] as const) {
      expect(forecastCallFor(rest)?.tool).toBe(forecastCallFor(mcp)?.tool);
      expect(forecastCallFor(rest)?.input).toEqual(forecastCallFor(mcp)?.input);
    }
  });

  it("puts a token on every request to Apify, and on no other request", () => {
    const requests: WireRequest[] = [
      ...LANE_IDS.flatMap((laneId) => callsFor(laneId).map((call) => call.wire)),
      ...SAMPLE_COMPARE_CELLS.map((cell) => cell.wire),
    ];
    for (const request of requests) {
      const hasToken = request.headers.Authorization !== undefined;
      expect(hasToken, request.url).toBe(APIFY_HOSTS.includes(toHost(request.url)));
    }
  });

  it("shows the four lanes in the compare view, in the grid's order", () => {
    expect(SAMPLE_COMPARE_CELLS.map((cell) => cell.lane.id)).toEqual([...LANE_IDS]);
  });
});
