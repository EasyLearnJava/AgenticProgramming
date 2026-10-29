/*
 * tests/unit/lanes/mcp-no-auth.test.ts: MCP · no auth against our own MCP server, run in this process: what a call
 * gives the page, the bypass secret (sent, never shown), and every way a call or the connection can end.
 */
import type { MCPClient } from "@ai-sdk/mcp";
import { createMcpHandler } from "mcp-handler";
import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ContractError, UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import type { Lane } from "@/lib/lanes/lane";
import { openMcpNoAuthLane } from "@/lib/lanes/mcp-no-auth";
import type { ToolResult } from "@/lib/types";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import { type FakeAnswer, hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

/** The lane, wired to our MCP server in-process, whose Open-Meteo calls get these answers (or this fetch). */
async function openWith(answers: FakeAnswer[] | typeof fetch, bypassSecret?: string) {
  const server = createMcpServerFetch(answers);
  const lane = await openMcpNoAuthLane({ origin: TEST_ORIGIN, bypassSecret, fetch: server.fetch });
  return { lane, requests: server.requests };
}

/** Runs one of the lane's tools, as streamText would, with this abort signal. */
async function call(lane: Lane, name: string, input: unknown, abortSignal?: AbortSignal): Promise<ToolResult<unknown>> {
  const tool = lane.tools[name];
  if (tool?.execute === undefined) {
    throw new Error(`The lane has no ${name} tool`);
  }
  return tool.execute(input, { toolCallId: "t1", messages: [], abortSignal, context: {} });
}

/** The events logged so far, read back from the JSON lines. */
function loggedEvents(written: { mock: { calls: unknown[][] } }): Record<string, unknown>[] {
  return written.mock.calls.map((each) => JSON.parse(String(each[0])));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("openMcpNoAuthLane", () => {
  it("connects to /api/mcp at this deployment's origin, and hands the model our four tools", async () => {
    const { lane, requests } = await openWith([]);
    expect(Object.keys(lane.tools).sort()).toEqual([
      "geocode_location",
      "get_air_quality",
      "get_current_weather",
      "get_forecast",
    ]);
    expect(new Set(requests.map((request) => request.url))).toEqual(new Set([`${TEST_ORIGIN}/api/mcp`]));
    await lane.close();
  });

  it("calls a tool through the server, and records the tools/call request it really sent", async () => {
    const { lane } = await openWith([{ fixture: "geocode-paris" }]);
    const result = await call(lane, "geocode_location", { query: "Paris" });
    expect(result.summary).toBe("Paris, Île-de-France Region, FR · 48.85, 2.35");
    expect(result.result).toMatchObject({ isAmbiguous: false });
    expect(result.call).toMatchObject({
      laneId: "mcp-no-auth",
      cache: "miss",
      wire: { method: "POST", url: `${TEST_ORIGIN}/api/mcp` },
    });
    expect(JSON.parse(result.call.wire.body ?? "{}")).toMatchObject({
      method: "tools/call",
      params: { name: "geocode_location", arguments: { query: "Paris" } },
    });
    await lane.close();
  });

  it("gives two calls made at once each its own request", async () => {
    const { lane } = await openWith([{ fixture: "geocode-paris" }, { fixture: "geocode-paris" }]);
    const [paris, lyon] = await Promise.all([
      call(lane, "geocode_location", { query: "Paris" }),
      call(lane, "geocode_location", { query: "Lyon" }),
    ]);
    expect(JSON.parse(paris?.call.wire.body ?? "{}").params.arguments).toEqual({ query: "Paris" });
    expect(JSON.parse(lyon?.call.wire.body ?? "{}").params.arguments).toEqual({ query: "Lyon" });
    await lane.close();
  });

  it("sends the bypass secret with every request, and never shows it", async () => {
    const { lane, requests } = await openWith([{ fixture: "geocode-paris" }], "s3cret-bypass");
    const result = await call(lane, "geocode_location", { query: "Paris" });
    expect(requests.every((request) => request.headers.get("x-vercel-protection-bypass") === "s3cret-bypass")).toBe(
      true,
    );
    expect(result.call.wire.headers["x-vercel-protection-bypass"]).toBe("<VERCEL_AUTOMATION_BYPASS_SECRET>");
    expect(JSON.stringify(result)).not.toContain("s3cret-bypass");
    await lane.close();
  });
});

describe("how a call through MCP · no auth can end", () => {
  it("a tool that failed on the server becomes the same error class as on REST", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fail = () => new Response("", { status: 503 });
    const { lane } = await openWith([fail, fail]);
    await expect(call(lane, "geocode_location", { query: "Paris" })).rejects.toBeInstanceOf(UpstreamUnavailableError);
    await lane.close();
  });

  it("past the tool's time budget: UpstreamTimeoutError, logged, as on REST", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { lane } = await openWith(hangingFetch);
    await expect(call(lane, "geocode_location", { query: "Paris" }, AbortSignal.timeout(50))).rejects.toBeInstanceOf(
      UpstreamTimeoutError,
    );
    expect(loggedEvents(written)).toContainEqual(
      expect.objectContaining({ event: "tool.failed", lane: "mcp-no-auth" }),
    );
    await lane.close();
  });

  it("a stop is passed on as it is, and not logged", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { lane } = await openWith(hangingFetch);
    const controller = new AbortController();
    const pending = call(lane, "geocode_location", { query: "Paris" }, controller.signal);
    setTimeout(() => controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" })), 30);
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(written).not.toHaveBeenCalled();
    await lane.close();
  });
});

describe("how connecting to MCP · no auth can fail", () => {
  it("a server that doesn't connect in time, or can't be reached; logged with the original error", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(
      openMcpNoAuthLane({ origin: TEST_ORIGIN, fetch: hangingFetch, connectTimeoutMs: 50 }),
    ).rejects.toBeInstanceOf(UpstreamTimeoutError);
    const refusing = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const error = await openMcpNoAuthLane({ origin: TEST_ORIGIN, fetch: refusing }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(UpstreamUnavailableError);
    expect((error as Error).cause).toBeDefined();
    expect(loggedEvents(written).map((line) => line.event)).toEqual(["lane.connect.failed", "lane.connect.failed"]);
  });

  it("a server without one of our tools: ContractError, logged", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const partial = createMcpHandler((server) => {
      server.registerTool("geocode_location", { inputSchema: z.object({ query: z.string() }) }, async () => ({
        content: [{ type: "text", text: "no places" }],
      }));
    });
    const serverFetch = (async (input: string | URL | Request, init?: RequestInit) =>
      partial(new Request(input, init))) as typeof fetch;
    const error = await openMcpNoAuthLane({ origin: TEST_ORIGIN, fetch: serverFetch }).catch((caught) => caught);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as Error).message).toBe(
      "Our MCP server doesn't list get_current_weather, get_forecast, get_air_quality.",
    );
    expect(loggedEvents(written)).toEqual([expect.objectContaining({ event: "lane.connect.failed" })]);
  });

  it("closes the client when listing the tools fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let closings = 0;
    const failingClient = {
      listTools: async () => {
        throw new Error("tools/list failed");
      },
      close: async () => {
        closings += 1;
      },
    } as unknown as MCPClient;
    await expect(
      openMcpNoAuthLane({ origin: TEST_ORIGIN, createClient: async () => failingClient }),
    ).rejects.toBeInstanceOf(UpstreamUnavailableError);
    expect(closings).toBe(1);
  });
});
