/*
 * lib/lanes/mcp-no-auth.ts: MCP · no auth. The same four tools, reached through our own MCP server at /api/mcp on
 * this deployment: the chat route is the MCP client, and the server calls Open-Meteo.
 */
import "server-only";
import { type CallToolResult, createMCPClient, type MCPClient, type MCPClientConfig } from "@ai-sdk/mcp";
import type { JSONValue, Tool } from "ai";
import { MCP_API_PATH, MCP_CONNECT_TIMEOUT_MS, REQUEST_ID_HEADER } from "@/lib/constants";
import { ContractError, toAppErrorByName, UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import { type Lane, toModelWeather } from "@/lib/lanes/lane";
import { type Logger, logger } from "@/lib/logger";
import type { ToolResult, WireRequest } from "@/lib/types";
import { once, timeoutSignal, toAbortKind } from "@/lib/utils";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import type { WeatherTool } from "@/lib/weather/weather-tool";

const LANE_ID = "mcp-no-auth";
const BYPASS_HEADER = "x-vercel-protection-bypass";
const MASKED_BYPASS_SECRET = "<VERCEL_AUTOMATION_BYPASS_SECRET>";

/** What the lane uses of an MCP client: listing the tools, calling one, and closing. */
type McpConnection = Pick<MCPClient, "listTools" | "callTool" | "close">;

type McpNoAuthOptions = {
  origin: string;
  requestId: string;
  log?: Logger;
  bypassSecret?: string;
  signal?: AbortSignal;
  fetch?: typeof fetch;
  now?: () => number;
  connectTimeoutMs?: number;
  createClient?: (config: MCPClientConfig) => Promise<McpConnection>;
};

/** Opens MCP · no auth: connects to /api/mcp, checks its tool list, and hands the model our four, called through it. */
export async function openMcpNoAuthLane({
  origin,
  requestId,
  log = logger,
  bypassSecret,
  signal,
  fetch: fetchMcp = fetch,
  now = performance.now.bind(performance),
  connectTimeoutMs = MCP_CONNECT_TIMEOUT_MS,
  createClient = createMCPClient,
}: McpNoAuthOptions): Promise<Lane> {
  // ① Where: /api/mcp on this same deployment, so a preview talks to its own MCP server.
  const url = `${origin}${MCP_API_PATH}`;
  // ② Auth: none. The bypass secret, when the project has one, gets the call past Vercel's Deployment Protection; it
  // isn't MCP auth. Every request also carries the chat's request id, so the server's log lines carry it too.
  const headers: Record<string, string> = {
    [REQUEST_ID_HEADER]: requestId,
    ...(bypassSecret ? { [BYPASS_HEADER]: bypassSecret } : {}),
  };
  // Every request the transport sends goes through this fetch, which keeps it for the chips' wire views.
  const sent: WireRequest[] = [];
  const recordingFetch = ((input: string | URL | Request, init?: RequestInit) => {
    sent.push(toWireRequest(input, init));
    return fetchMcp(input, init);
  }) as typeof fetch;
  // ③ Tools: connect within 3 s; the server's list must hold our four, and a tool it adds never reaches the model.
  // Either way, one lane.connect line with the time it took; a failure's own line is the chat route's, which answers.
  const connect: ConnectState = {
    connectSignal: timeoutSignal(connectTimeoutMs, signal),
    connectTimeoutMs,
    signal,
    logConnect: ((startedAt) => (fields) => {
      log.info({ event: "lane.connect", ms: Math.round(now() - startedAt), ...fields });
    })(now()),
  };
  const client = await createClient({
    transport: { type: "http", url, headers, fetch: recordingFetch },
    initializationOptions: { signal: connect.connectSignal },
  }).catch((error: unknown) => {
    throw toConnectError(error, connect);
  });
  const close = once(() => client.close());
  try {
    const { tools: listed } = await client.listTools({ options: { signal: connect.connectSignal } });
    const missing = Object.keys(OPEN_METEO_TOOLS).filter((name) => !listed.some((tool) => tool.name === name));
    if (missing.length > 0) {
      throw new ContractError(`Our MCP server doesn't list ${missing.join(", ")}.`);
    }
    connect.logConnect({ status: "ok", tools: listed.length });
  } catch (error) {
    await close();
    throw toConnectError(error, connect);
  }
  const tools = {
    geocode_location: toMcpTool(OPEN_METEO_TOOLS.geocode_location, client, sent, now),
    get_current_weather: toMcpTool(OPEN_METEO_TOOLS.get_current_weather, client, sent, now),
    get_forecast: toMcpTool(OPEN_METEO_TOOLS.get_forecast, client, sent, now),
    get_air_quality: toMcpTool(OPEN_METEO_TOOLS.get_air_quality, client, sent, now),
  };
  // ⑥ Clean-up: close the connection however the answer ends, and only once.
  return { id: LANE_ID, tools, close };
}

/** Connecting: its own time limit, the request's signal, and the lane.connect line, which knows when it started. */
type ConnectState = {
  connectSignal: AbortSignal;
  connectTimeoutMs: number;
  signal: AbortSignal | undefined;
  logConnect: (fields: Record<string, unknown>) => void;
};

/**
 * A failure to connect or list the tools, as one of our classes, keeping the original as its cause (a preview's 401
 * from Deployment Protection, say), which the chat route logs; lane.connect says it failed. A stop is passed on as it
 * is.
 */
function toConnectError(
  error: unknown,
  { connectSignal, connectTimeoutMs, signal, logConnect }: ConnectState,
): unknown {
  if (toAbortKind(signal) === "stop") {
    return error;
  }
  let failure: ContractError | UpstreamTimeoutError | UpstreamUnavailableError;
  if (error instanceof ContractError) {
    failure = error;
  } else if (connectSignal.aborted) {
    failure = new UpstreamTimeoutError(`Our MCP server didn't connect within ${connectTimeoutMs} ms.`, {
      cause: error,
    });
  } else {
    failure = new UpstreamUnavailableError("Our MCP server can't be reached.", { cause: error });
  }
  logConnect({ status: "failed", errorClass: failure.name });
  return failure;
}

/** A request as the MCP transport sends it, with the bypass secret masked: what a chip's wire view shows. */
function toWireRequest(input: string | URL | Request, init?: RequestInit): WireRequest {
  const headers = Object.fromEntries(
    [...new Headers(init?.headers).entries()].map(([name, value]) => [
      name,
      name === BYPASS_HEADER ? MASKED_BYPASS_SECRET : value,
    ]),
  );
  const body = typeof init?.body === "string" ? init.body : undefined;
  return { method: init?.method === "GET" ? "GET" : "POST", url: String(input), headers, body };
}

/** The tools/call request that carried a call: the last one with this tool's name and these arguments. */
function findToolsCall(sent: readonly WireRequest[], name: string, input: unknown): WireRequest | undefined {
  const wanted = JSON.stringify(input);
  return sent.findLast((request) => {
    const message: unknown = request.body === undefined ? undefined : JSON.parse(request.body);
    if (typeof message !== "object" || message === null || !("method" in message) || !("params" in message)) {
      return false;
    }
    const params = message.params as { name?: unknown; arguments?: unknown };
    return message.method === "tools/call" && params.name === name && JSON.stringify(params.arguments) === wanted;
  });
}

/** A tool result's text parts, joined: our tools' one-line summary. A result without a content list has no text. */
function toResultText(result: CallToolResult): string {
  const content: unknown = "content" in result ? result.content : undefined;
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .map((part: unknown) =>
      typeof part === "object" && part !== null && "text" in part && typeof part.text === "string" ? part.text : "",
    )
    .join("");
}

/** One of our tools as an AI SDK tool that calls it through the MCP server, and records how the call went. */
function toMcpTool<Name extends string, Input, Output extends JSONValue>(
  definition: WeatherTool<Name, Input, Output>,
  client: McpConnection,
  sent: readonly WireRequest[],
  now: () => number,
): Tool<Input, ToolResult<Output>> {
  return {
    description: definition.description,
    inputSchema: definition.inputSchema,
    // ④ The call: a JSON-RPC tools/call over Streamable HTTP, with the tool's abort signal (Stop, budget).
    execute: async (input: Input, { abortSignal }: { abortSignal?: AbortSignal }): Promise<ToolResult<Output>> => {
      const startedAt = now();
      const result = await client
        .callTool({
          name: definition.name,
          arguments: input as Record<string, unknown>,
          options: { signal: abortSignal },
        })
        .catch((error: unknown) => {
          // The server didn't answer: a stop is passed on as the signal's own reason, as on REST (the MCP client wraps
          // it); anything else becomes one of our classes, as on REST, which the chat logs, as for every lane (a tool
          // that failed on the server is logged there too, by the server).
          const abortKind = toAbortKind(abortSignal);
          if (abortKind === "stop") {
            throw abortSignal?.reason;
          }
          throw abortKind === "timeout"
            ? new UpstreamTimeoutError("Our MCP server didn't answer within the tool's time budget.", { cause: error })
            : new UpstreamUnavailableError("Our MCP server can't be reached.", { cause: error });
        });
      const meta = (result._meta ?? {}) as { cache?: unknown; errorClass?: unknown };
      const text = toResultText(result);
      if (result.isError === true) {
        throw toAppErrorByName(typeof meta.errorClass === "string" ? meta.errorClass : undefined, text);
      }
      // ⑤ The result: the server's structured content, which is the tool's own output, and its one-line summary.
      const wire = findToolsCall(sent, definition.name, input);
      if (result.structuredContent === undefined || wire === undefined) {
        throw new ContractError(`Our MCP server's ${definition.name} answer is missing its content or its request.`);
      }
      return {
        result: result.structuredContent as Output,
        summary: text,
        call: {
          laneId: LANE_ID,
          wire,
          cache: meta.cache === "hit" ? "hit" : "miss",
          durationMs: Math.round(now() - startedAt),
        },
      };
    },
    // The model reads only the weather; the request and the time are for the page.
    toModelOutput: toModelWeather,
  };
}
