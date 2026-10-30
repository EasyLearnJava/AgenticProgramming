/*
 * tests/unit/app/api/mcp/route.test.ts: GET and POST /api/mcp, the real route, through an MCP client: it names itself
 * and lists the four tools; and once it has answered a tool call, it sends its lines out, the tool's line included.
 * Open-Meteo is a stand-in that can't be reached, so nothing leaves the machine.
 */
import { createMCPClient } from "@ai-sdk/mcp";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/mcp/route";
import type { LogLine } from "@/tests/stubs/log-stand-ins";

// The app's logger, swapped for one whose lines the tests can read; and flushLogs, for one that notes how many lines
// had been written when it was called.
const { lines, flushedAt } = vi.hoisted(() => ({ lines: [] as LogLine[], flushedAt: [] as number[] }));
vi.mock("@/lib/logger", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/logger")>();
  const write = (line: string) => {
    lines.push(JSON.parse(line) as LogLine);
  };
  return {
    ...actual,
    logger: actual.createLogger({ level: "info", destination: { write } }),
    flushLogs: async () => {
      flushedAt.push(lines.length);
    },
  };
});

// Vercel's waitUntil, swapped for one that keeps what it's given: what the route keeps the function alive for.
const { kept } = vi.hoisted(() => ({ kept: [] as Promise<unknown>[] }));
vi.mock("@vercel/functions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vercel/functions")>();
  return {
    ...actual,
    waitUntil: (promise: Promise<unknown>) => {
      kept.push(promise);
    },
  };
});

// Open-Meteo, swapped for one that can't be reached: each call fails at once.
vi.mock("@/lib/upstream/open-meteo", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/upstream/open-meteo")>();
  const { UpstreamUnavailableError } = await import("@/lib/errors");
  const unreachable = async () => {
    throw new UpstreamUnavailableError("Open-Meteo can't be reached.");
  };
  return {
    ...actual,
    createOpenMeteoClient: () => ({
      searchPlaces: unreachable,
      getForecast: unreachable,
      getCurrentWeather: unreachable,
      getAirQuality: unreachable,
    }),
  };
});

beforeEach(() => {
  lines.length = 0;
  flushedAt.length = 0;
  kept.length = 0;
});

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

  it("sends its lines out once it has answered a tool call, the tool's own line included", async () => {
    const client = await createMCPClient({
      transport: { type: "http", url: "https://nimbus.test/api/mcp", fetch: routeFetch },
    });
    lines.length = 0;
    flushedAt.length = 0;
    const result = await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
    expect(result.isError).toBe(true);
    await Promise.all(kept);
    expect(lines.map((line) => `${String(line.level)} ${String(line.event)}`)).toEqual(["warn mcp.call"]);
    expect(flushedAt).toEqual([1]);
    await client.close();
  });
});
