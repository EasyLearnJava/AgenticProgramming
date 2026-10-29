/*
 * tests/unit/weather/register-tools.test.ts: our MCP server's four tools, through a real MCP client: the list, pinned
 * to our definitions (the contract test), a call's answer, a failure's class, and the server's own log lines.
 */
import { createMCPClient, type MCPClient } from "@ai-sdk/mcp";
import { createMcpHandler } from "mcp-handler";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import type { Logger } from "@/lib/logger";
import type { OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import { registerTools } from "@/lib/weather/register-tools";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import type { FakeAnswer } from "@/tests/stubs/open-meteo-stand-ins";

/**
 * An MCP client connected to our server, in-process, whose Open-Meteo calls get these answers; the server logs to the
 * logger given, and the client sends these headers.
 */
async function connect(answers: FakeAnswer[] = [], log?: Logger, headers?: Record<string, string>): Promise<MCPClient> {
  const { fetch } = createMcpServerFetch(answers, log);
  return createMCPClient({ transport: { type: "http", url: `${TEST_ORIGIN}/api/mcp`, headers, fetch } });
}

describe("registerTools, through an MCP client", () => {
  it("names itself, and lists exactly our four tools, read-only, each with our own input schema", async () => {
    const client = await connect();
    expect(client.serverInfo).toMatchObject({ name: "nimbus-weather", version: "1.0.0" });
    const { tools } = await client.listTools();
    expect(tools.map((tool) => tool.name).sort()).toEqual(Object.keys(OPEN_METEO_TOOLS).sort());
    for (const tool of tools) {
      const definition = Object.values(OPEN_METEO_TOOLS).find((each) => each.name === tool.name);
      const ours = z.toJSONSchema(definition?.inputSchema ?? z.never()) as { properties?: object; required?: string[] };
      expect(tool.description).toBe(definition?.description);
      expect(tool.annotations).toMatchObject({ readOnlyHint: true, openWorldHint: true });
      expect(Object.keys(tool.inputSchema.properties ?? {}).sort()).toEqual(Object.keys(ours.properties ?? {}).sort());
      const listedRequired: unknown = tool.inputSchema.required;
      expect(Array.isArray(listedRequired) ? [...listedRequired].sort() : []).toEqual(
        [...(ours.required ?? [])].sort(),
      );
    }
    await client.close();
  });

  it("answers a call with the weather as structured content, its summary as text, and the request in _meta", async () => {
    const client = await connect([{ fixture: "geocode-paris" }]);
    const result = await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
    expect(result.isError).not.toBe(true);
    expect(result.structuredContent).toMatchObject({ isAmbiguous: false });
    expect(result).toMatchObject({
      content: [{ type: "text", text: "Paris, Île-de-France Region, FR · 48.85, 2.35" }],
      _meta: { cache: "miss", request: { method: "GET", headers: { accept: "application/json" } } },
    });
    await client.close();
  });

  it("logs each call on the server: mcp.call, under the id the chat's MCP lane sent, and the request's own", async () => {
    const { log, lines } = createTestLog();
    // On Vercel, x-vercel-id is the platform's own id for this request to /api/mcp; here the test sends it.
    const client = await connect([{ fixture: "geocode-paris" }], log, {
      "x-request-id": "iad1::abcde-1730-7f3a9c01",
      "x-vercel-id": "iad1::iad1::fghij-1730-0b1c2d3e",
    });
    await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
    expect(lines.map((line) => line.event)).toEqual(["upstream.http", "mcp.call"]);
    expect(lines.at(-1)).toMatchObject({
      level: "info",
      requestId: "iad1::abcde-1730-7f3a9c01",
      invocationId: "iad1::iad1::fghij-1730-0b1c2d3e",
      route: "/api/mcp",
      tool: "geocode_location",
      status: "ok",
      cache: "miss",
    });
    expect(lines[0]?.requestId).toBe("iad1::abcde-1730-7f3a9c01");
    await client.close();
  });

  it("answers a failed call with isError, our message and the error's class, and logs it at the class's level", async () => {
    const { log, lines } = createTestLog();
    const fail = () => new Response("", { status: 503 });
    const client = await connect([fail, fail], log);
    const result = await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
    expect(result).toMatchObject({
      isError: true,
      content: [{ type: "text", text: "Open-Meteo answered 503." }],
      _meta: { errorClass: "UpstreamUnavailableError" },
    });
    expect(lines.at(-1)).toMatchObject({
      level: "warn",
      event: "mcp.call",
      status: "failed",
      errorClass: "UpstreamUnavailableError",
      requestId: expect.stringMatching(/^[0-9a-f]{16}$/),
    });
    await client.close();
  });
});

describe("registerTools, for an error that isn't ours", () => {
  it("sends a fixed sentence, not the error's own text, since any MCP client can read it, and logs a bug", async () => {
    const { log, lines } = createTestLog();
    const broken = {
      searchPlaces: async () => {
        throw new TypeError("Cannot read properties of undefined (reading 'secret')");
      },
    } as unknown as OpenMeteoClient;
    const handler = createMcpHandler((server) => registerTools(server, { openMeteo: broken, log }));
    const serverFetch = (async (input: string | URL | Request, init?: RequestInit) =>
      handler(new Request(input, init))) as typeof fetch;
    const client = await createMCPClient({
      transport: { type: "http", url: `${TEST_ORIGIN}/api/mcp`, fetch: serverFetch },
    });
    const result = await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
    expect(result).toMatchObject({
      isError: true,
      content: [{ type: "text", text: "The weather tool failed unexpectedly." }],
      _meta: { errorClass: "UnexpectedError" },
    });
    expect(JSON.stringify(result)).not.toContain("secret");
    expect(lines).toEqual([
      expect.objectContaining({
        level: "error",
        event: "mcp.call",
        errorClass: "UnexpectedError",
        causeClass: "TypeError",
      }),
    ]);
    await client.close();
  });
});
