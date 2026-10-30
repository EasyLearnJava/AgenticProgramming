/*
 * tests/unit/chat/lane-examples.test.ts: the compare view's examples keep the plan's rules: within a pair, the same
 * tool with the same input, only the door changing; a token to Apify and to no other host. And the MCP doors' requests
 * name AI SDK's client as its real requests do.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { COMPARE_CELLS } from "@/lib/chat/lane-examples";
import { LANE_IDS } from "@/lib/constants";
import { AuthError } from "@/lib/errors";
import type { CompareCell, LaneId } from "@/lib/types";
import { type ActorRunInput, toActorRequest } from "@/lib/upstream/apify";
import { createApifyMcpClient } from "@/lib/upstream/apify-mcp";
import { toForecastRequest } from "@/lib/upstream/open-meteo";
import { toHost } from "@/lib/utils";
import { createApifyMcp401Fetch } from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";

const APIFY_HOSTS = ["api.apify.com", "mcp.apify.com"];
// The Actor's input for the plan's Paris question, as the auth lanes send it.
const PARIS_RUN: ActorRunInput = {
  locations: [{ name: "Paris", latitude: 48.85, longitude: 2.35 }],
  forecastDays: 2,
  mode: "hourly",
};

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

  it("sends the auth pair the same tool, Actor input and limits: in REST's URL, in call-actor's callOptions", () => {
    expect(cellFor("rest-auth").tool).toBe(cellFor("mcp-auth").tool);
    const limits = new URL(cellFor("rest-auth").wire.url).searchParams;
    expect(toolsCallArguments(cellFor("mcp-auth"))).toEqual({
      actor: "gochujang/open-meteo-weather-forecast",
      input: JSON.parse(cellFor("rest-auth").wire.body ?? ""),
      waitSecs: 18,
      callOptions: {
        build: limits.get("build"),
        timeout: Number(limits.get("timeout")),
        maxTotalChargeUsd: Number(limits.get("maxTotalChargeUsd")),
      },
    });
    expect(cellFor("mcp-auth").wire).toMatchObject({
      url: "https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast",
      headers: { authorization: "Bearer <APIFY_TOKEN>", "mcp-session-id": "<session id>" },
    });
  });

  it("puts a token on every request to Apify, and on no other request, always masked", () => {
    for (const { wire } of COMPARE_CELLS) {
      const authorization = Object.entries(wire.headers).find(([name]) => name.toLowerCase() === "authorization")?.[1];
      expect(authorization !== undefined, wire.url).toBe(APIFY_HOSTS.includes(toHost(wire.url)));
      expect(authorization ?? "Bearer <APIFY_TOKEN>").toBe("Bearer <APIFY_TOKEN>");
    }
  });

  it("shows REST · with auth's request as the Apify client builds it: the build, time and cost in the URL", () => {
    const { wire, tool } = cellFor("rest-auth");
    expect(tool).toBe("gochujang--open-meteo-weather-forecast");
    expect(wire).toEqual(toActorRequest(PARIS_RUN));
    expect(wire.url).toBe(
      "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items" +
        "?build=1.0.9&timeout=18&maxTotalChargeUsd=0.01",
    );
  });

  it("names AI SDK's MCP client on both MCP doors as its real requests do, with the deployment's Node", async () => {
    // AI SDK's own client, asking a stand-in that answers with Apify MCP's real 401: the user-agent it really sends.
    const apify = createApifyMcp401Fetch();
    const client = createApifyMcpClient({ token: "test-token-not-real", fetch: apify.fetch });
    await expect(client.runActor(PARIS_RUN, { log: createTestLog().log })).rejects.toBeInstanceOf(AuthError);
    const sent = new Headers(apify.inits[0]?.headers).get("user-agent");
    // Node's part is the deployment's, which package.json pins by its major version ("22.x"); the tests' may differ.
    const { engines }: { engines: { node: string } } = JSON.parse(
      readFileSync(path.join(import.meta.dirname, "..", "..", "..", "package.json"), "utf8"),
    );
    const deployed = sent?.replace(/node\.js\/\d+/, `node.js/${engines.node.split(".")[0]}`);
    for (const laneId of ["mcp-no-auth", "mcp-auth"] as const) {
      expect(cellFor(laneId).wire.headers["user-agent"], laneId).toBe(deployed);
    }
  });
});
