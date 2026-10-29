/*
 * tests/unit/app/api/mcp/route.test.ts: GET and POST /api/mcp, the real route, through an MCP client: it names itself
 * and lists the four tools. Nothing is called, so nothing reaches Open-Meteo.
 */
import { createMCPClient } from "@ai-sdk/mcp";
import { describe, expect, it } from "vitest";
import { GET, POST } from "@/app/api/mcp/route";

/** A fetch that hands each request to the route, as Next.js would. */
const routeFetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const request = new Request(input, init);
  return request.method === "GET" ? GET(request) : POST(request);
}) as typeof fetch;

describe("/api/mcp", () => {
  it("is an MCP server named nimbus-weather, with the four weather tools", async () => {
    const client = await createMCPClient({
      transport: { type: "http", url: "https://nimbus.test/api/mcp", fetch: routeFetch },
    });
    expect(client.serverInfo).toMatchObject({ name: "nimbus-weather" });
    const { tools } = await client.listTools();
    expect(tools.map((tool) => tool.name).sort()).toEqual([
      "geocode_location",
      "get_air_quality",
      "get_current_weather",
      "get_forecast",
    ]);
    await client.close();
  });
});
