/*
 * tests/unit/weather/register-tools.test.ts: our MCP server's four tools, through a real MCP client: the list, pinned
 * to our definitions (the contract test), a call's answer, and a failure's class.
 */
import { createMCPClient, type MCPClient } from "@ai-sdk/mcp";
import { createMcpHandler } from "mcp-handler";
import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import type { OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import { registerTools } from "@/lib/weather/register-tools";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import type { FakeAnswer } from "@/tests/stubs/open-meteo-stand-ins";

/** An MCP client connected to our server, in-process, whose Open-Meteo calls get these answers. */
async function connect(answers: FakeAnswer[] = []): Promise<MCPClient> {
  const { fetch } = createMcpServerFetch(answers);
  return createMCPClient({ transport: { type: "http", url: `${TEST_ORIGIN}/api/mcp`, fetch } });
}

afterEach(() => {
  vi.restoreAllMocks();
});

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

  it("answers a failed call with isError, our message and the error's class, and logs it on the server", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fail = () => new Response("", { status: 503 });
    const client = await connect([fail, fail]);
    const result = await client.callTool({ name: "geocode_location", arguments: { query: "Paris" } });
    expect(result).toMatchObject({
      isError: true,
      content: [{ type: "text", text: "Open-Meteo answered 503." }],
      _meta: { errorClass: "UpstreamUnavailableError" },
    });
    expect(JSON.parse(String(written.mock.calls[0]?.[0]))).toMatchObject({ event: "tool.failed", door: "mcp" });
    await client.close();
  });
});

describe("registerTools, for an error that isn't ours", () => {
  it("sends a fixed sentence, not the error's own text, since any MCP client can read it", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const broken = {
      searchPlaces: async () => {
        throw new TypeError("Cannot read properties of undefined (reading 'secret')");
      },
    } as unknown as OpenMeteoClient;
    const handler = createMcpHandler((server) => registerTools(server, { openMeteo: broken }));
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
    await client.close();
  });
});
