/*
 * lib/weather/register-tools.ts: puts our four weather tools on an MCP server: the very definitions REST · no auth runs,
 * so the two no-auth doors can't drift apart. Each answers with the weather as structured content, its one-line
 * summary as text, and, in _meta, the request to Open-Meteo and whether the cache answered; a failure says its class.
 * Each call logs one mcp.call line, under the chat's request id when the MCP lane sent it.
 */
import "server-only";
import type { CallToolResult, McpServer } from "@modelcontextprotocol/server";
import { MCP_API_PATH, REQUEST_ID_HEADER, VERCEL_ID_HEADER } from "@/lib/constants";
import { AbortedError, type AppError, toAppError, UnexpectedError } from "@/lib/errors";
import { type Logger, logFailure, logger } from "@/lib/logger";
import { createOpenMeteoClient, type OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { toRequestId } from "@/lib/utils";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import type { WeatherTool } from "@/lib/weather/weather-tool";

type RegisterToolsOptions = { openMeteo?: OpenMeteoClient; log?: Logger; now?: () => number };

/** What each tool uses: the Open-Meteo client, the server's logger, and a clock for the call's time. */
type ServerDeps = { openMeteo: OpenMeteoClient; log: Logger; now: () => number };

const UNEXPECTED_FAILURE_MESSAGE = "The weather tool failed unexpectedly.";

/**
 * A failed call, as MCP sends it: our own error's message and class by name, which the MCP lane turns back into that
 * class; a bug gets a fixed sentence, since any MCP client can read it.
 */
function toFailedResult(error: AppError): CallToolResult {
  const text = error instanceof UnexpectedError ? UNEXPECTED_FAILURE_MESSAGE : error.message;
  return { isError: true, content: [{ type: "text", text }], _meta: { errorClass: error.name } };
}

/**
 * A call's logger: under the chat's request id when the MCP lane sent one (x-request-id), else this request's own id;
 * and always with this request's own id, Vercel's (else a new one), as invocationId: the server is public, so a caller
 * can send any x-request-id, and its lines must still be told from the chat's own.
 */
function toCallLog(log: Logger, request: Request | undefined, tool: string): Logger {
  const headers = request?.headers;
  const invocationId = toRequestId(headers?.get(VERCEL_ID_HEADER) ?? null);
  const requestId = toRequestId(headers?.get(REQUEST_ID_HEADER) ?? null, invocationId);
  return log.child({ requestId, invocationId, route: MCP_API_PATH, tool });
}

/** Registers one tool: read-only, reaching outside (Open-Meteo), as its annotations say. */
function registerTool<Name extends string, Input, Output extends Record<string, unknown>>(
  server: McpServer,
  definition: WeatherTool<Name, Input, Output>,
  { openMeteo, log: serverLog, now }: ServerDeps,
): void {
  server.registerTool(
    definition.name,
    {
      description: definition.description,
      inputSchema: definition.inputSchema,
      annotations: { readOnlyHint: true, openWorldHint: true },
    },
    async (input: Input, ctx): Promise<CallToolResult> => {
      const log = toCallLog(serverLog, ctx.http?.req, definition.name);
      const startedAt = now();
      try {
        const run = await definition.run(input, { openMeteo, signal: ctx.mcpReq.signal, log });
        log.info({ event: "mcp.call", status: "ok", ms: Math.round(now() - startedAt), cache: run.cache });
        return {
          content: [{ type: "text", text: definition.summarize(run.output) }],
          structuredContent: run.output,
          _meta: { request: run.request, cache: run.cache },
        };
      } catch (error) {
        // A failure is logged here, where it's handled, unless the client went away; then it goes back as a result.
        const failure = toAppError(error, ctx.mcpReq.signal);
        if (!(failure instanceof AbortedError)) {
          logFailure(log, "mcp.call", failure, { ms: Math.round(now() - startedAt) });
        }
        return toFailedResult(failure);
      }
    },
  );
}

/** Registers the four Open-Meteo tools on an MCP server. */
export function registerTools(
  server: McpServer,
  {
    openMeteo = createOpenMeteoClient(),
    log = logger,
    now = performance.now.bind(performance),
  }: RegisterToolsOptions = {},
): void {
  const deps: ServerDeps = { openMeteo, log, now };
  registerTool(server, OPEN_METEO_TOOLS.geocode_location, deps);
  registerTool(server, OPEN_METEO_TOOLS.get_current_weather, deps);
  registerTool(server, OPEN_METEO_TOOLS.get_forecast, deps);
  registerTool(server, OPEN_METEO_TOOLS.get_air_quality, deps);
}
