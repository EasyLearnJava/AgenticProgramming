/*
 * lib/lanes/mcp-no-auth.ts: MCP · no auth. The same four tools, reached through our own MCP server at /api/mcp on
 * this deployment: the chat route is the MCP client, and the server calls Open-Meteo. MCP · with auth reaches our
 * server the same way, for geocoding and its fallback, so connecting and calling a tool are exported here.
 */
import "server-only";
import { createMCPClient, type MCPClientConfig } from "@ai-sdk/mcp";
import type { JSONValue, Tool } from "ai";
import { MCP_API_PATH, MCP_CONNECT_TIMEOUT_MS, REQUEST_ID_HEADER } from "@/lib/constants";
import { ContractError, toAppErrorByName, UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import { type Lane, toModelWeather } from "@/lib/lanes/lane";
import { type Logger, logger } from "@/lib/logger";
import type { LiveLaneId, McpClient, ToolResult, WireRequest } from "@/lib/types";
import { findToolsCall, once, timeoutSignal, toAbortKind, toResultText, toWireRequest } from "@/lib/utils";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import type { WeatherTool } from "@/lib/weather/weather-tool";

const LANE_ID = "mcp-no-auth";
const BYPASS_HEADER = "x-vercel-protection-bypass";
// What the page sees instead of the bypass secret.
const MASKS: Readonly<Record<string, string>> = { [BYPASS_HEADER]: "<VERCEL_AUTOMATION_BYPASS_SECRET>" };

/** An open connection to our MCP server: the client, every request it has sent (for the chips), and closing it once. */
export type McpConnection = { client: McpClient; sent: readonly WireRequest[]; close: () => Promise<void> };

export type OurMcpOptions = {
  origin: string;
  requestId: string;
  log?: Logger;
  bypassSecret?: string;
  signal?: AbortSignal;
  fetch?: typeof fetch;
  now?: () => number;
  connectTimeoutMs?: number;
  createClient?: (config: MCPClientConfig) => Promise<McpClient>;
};

/** Opens MCP · no auth: connects to /api/mcp, checks its tool list, and hands the model our four, called through it. */
export async function openMcpNoAuthLane(options: OurMcpOptions): Promise<Lane> {
  const { now = performance.now.bind(performance) } = options;
  const connection = await connectToOurMcpServer(options);
  const tools = {
    geocode_location: toMcpTool(OPEN_METEO_TOOLS.geocode_location, connection, now, LANE_ID),
    get_current_weather: toMcpTool(OPEN_METEO_TOOLS.get_current_weather, connection, now, LANE_ID),
    get_forecast: toMcpTool(OPEN_METEO_TOOLS.get_forecast, connection, now, LANE_ID),
    get_air_quality: toMcpTool(OPEN_METEO_TOOLS.get_air_quality, connection, now, LANE_ID),
  };
  // ⑥ Clean-up: close the connection however the answer ends, and only once.
  return { id: LANE_ID, tools, close: connection.close };
}

/** Connects to our MCP server at /api/mcp on this deployment, and checks that it lists our four tools. */
export async function connectToOurMcpServer({
  origin,
  requestId,
  log = logger,
  bypassSecret,
  signal,
  fetch: fetchMcp = fetch,
  now = performance.now.bind(performance),
  connectTimeoutMs = MCP_CONNECT_TIMEOUT_MS,
  createClient = createMCPClient,
}: OurMcpOptions): Promise<McpConnection> {
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
    sent.push(toWireRequest(input, init, MASKS));
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
  return { client, sent, close };
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

/**
 * One of our tools, called through our MCP server: its result, with the request that carried it and how long it took,
 * recorded as the given lane's call.
 */
export async function callOurMcpTool<Name extends string, Input, Output extends JSONValue>(
  definition: WeatherTool<Name, Input, Output>,
  { client, sent }: McpConnection,
  input: Input,
  { laneId, signal, now }: { laneId: LiveLaneId; signal: AbortSignal | undefined; now: () => number },
): Promise<ToolResult<Output>> {
  const startedAt = now();
  // ④ The call: a JSON-RPC tools/call over Streamable HTTP, with the tool's abort signal (Stop, budget).
  const result = await client
    .callTool({ name: definition.name, arguments: input as Record<string, unknown>, options: { signal } })
    .catch((error: unknown) => {
      // The server didn't answer: a stop is passed on as the signal's own reason, as on REST (the MCP client wraps
      // it); anything else becomes one of our classes, as on REST, which the chat logs, as for every lane (a tool that
      // failed on the server is logged there too, by the server).
      const abortKind = toAbortKind(signal);
      if (abortKind === "stop") {
        throw signal?.reason;
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
    call: { laneId, wire, cache: meta.cache === "hit" ? "hit" : "miss", durationMs: Math.round(now() - startedAt) },
  };
}

/** One of our tools as an AI SDK tool that calls it through our MCP server, recorded as the given lane's call. */
export function toMcpTool<Name extends string, Input, Output extends JSONValue>(
  definition: WeatherTool<Name, Input, Output>,
  connection: McpConnection,
  now: () => number,
  laneId: LiveLaneId,
): Tool<Input, ToolResult<Output>> {
  return {
    description: definition.description,
    inputSchema: definition.inputSchema,
    execute: (input: Input, { abortSignal }: { abortSignal?: AbortSignal }): Promise<ToolResult<Output>> =>
      callOurMcpTool(definition, connection, input, { laneId, signal: abortSignal, now }),
    // The model reads only the weather; the request and the time are for the page.
    toModelOutput: toModelWeather,
  };
}
