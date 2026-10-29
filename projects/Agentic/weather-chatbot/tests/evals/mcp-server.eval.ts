/*
 * tests/evals/mcp-server.eval.ts: our MCP server on a running deployment, through a real MCP client, as any MCP client
 * (Claude, Cursor, the MCP Inspector) would use it: it lists the four tools, calls one, and the handshake and a call
 * are timed. It calls Open-Meteo, not the model. Runs only with EVAL_BASE_URL set.
 */
import { createMCPClient } from "@ai-sdk/mcp";
import { describe, expect, it } from "vitest";

const BASE_URL = process.env.EVAL_BASE_URL;
const BYPASS_SECRET = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
const CALLS = 3;

/** Milliseconds since a start time, rounded. */
function msSince(startedAt: number): number {
  return Math.round(performance.now() - startedAt);
}

describe.skipIf(!BASE_URL)(`the MCP server at ${BASE_URL ?? "(EVAL_BASE_URL not set)"}/api/mcp`, () => {
  it("connects, lists the four weather tools, and answers a geocoding call; with the times", async () => {
    // ① The handshake: connecting, then listing the tools.
    const connectStart = performance.now();
    const client = await createMCPClient({
      transport: {
        type: "http",
        url: `${BASE_URL}/api/mcp`,
        headers: BYPASS_SECRET ? { "x-vercel-protection-bypass": BYPASS_SECRET } : {},
      },
    });
    const connectMs = msSince(connectStart);
    const listStart = performance.now();
    const { tools } = await client.listTools();
    const listMs = msSince(listStart);
    expect(client.serverInfo).toMatchObject({ name: "nimbus-weather" });
    expect(tools.map((tool) => tool.name).sort()).toEqual([
      "geocode_location",
      "get_air_quality",
      "get_current_weather",
      "get_forecast",
    ]);
    // ② The hop: the same call, a few times (the first may miss the cache; the rest should hit it).
    const callMs: number[] = [];
    for (let i = 0; i < CALLS; i += 1) {
      const callStart = performance.now();
      const result = await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
      callMs.push(msSince(callStart));
      expect(result.isError).not.toBe(true);
      expect(result.structuredContent).toMatchObject({ isAmbiguous: false });
    }
    await client.close();
    // ③ The times, for the docs: printed, since they're measurements, not pass-or-fail.
    process.stdout.write(
      `MCP timings: connect ${connectMs} ms, tools/list ${listMs} ms, tools/call ${callMs.join(", ")} ms\n`,
    );
  });
});
