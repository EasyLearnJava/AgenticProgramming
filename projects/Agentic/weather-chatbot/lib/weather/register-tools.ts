/*
 * lib/weather/register-tools.ts: puts our four weather tools on an MCP server: the very definitions REST · no auth runs,
 * so the two no-auth doors can't drift apart. Each answers with the weather as structured content, its one-line
 * summary as text, and, in _meta, the request to Open-Meteo and whether the cache answered; a failure says its class.
 */
import "server-only";
import type { CallToolResult, McpServer } from "@modelcontextprotocol/server";
import { AppError } from "@/lib/errors";
import { logError } from "@/lib/logger";
import { createOpenMeteoClient, type OpenMeteoClient } from "@/lib/upstream/open-meteo";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";
import type { WeatherTool } from "@/lib/weather/weather-tool";

type RegisterToolsOptions = { openMeteo?: OpenMeteoClient };

const UNEXPECTED_FAILURE_MESSAGE = "The weather tool failed unexpectedly.";

/**
 * A failed call, as MCP sends it: our own error's message and class by name, which the MCP lane turns back into that
 * class; anything else (a bug, say) gets a fixed sentence, since any MCP client can read it.
 */
function toFailedResult(error: unknown): CallToolResult {
  const isOurs = error instanceof AppError;
  const text = isOurs ? error.message : UNEXPECTED_FAILURE_MESSAGE;
  return {
    isError: true,
    content: [{ type: "text", text }],
    _meta: { errorClass: isOurs ? error.name : "UnexpectedError" },
  };
}

/** Registers one tool: read-only, reaching outside (Open-Meteo), as its annotations say. */
function registerTool<Name extends string, Input, Output extends Record<string, unknown>>(
  server: McpServer,
  definition: WeatherTool<Name, Input, Output>,
  openMeteo: OpenMeteoClient,
): void {
  server.registerTool(
    definition.name,
    {
      description: definition.description,
      inputSchema: definition.inputSchema,
      annotations: { readOnlyHint: true, openWorldHint: true },
    },
    async (input: Input, ctx): Promise<CallToolResult> => {
      try {
        const run = await definition.run(input, { openMeteo, signal: ctx.mcpReq.signal });
        return {
          content: [{ type: "text", text: definition.summarize(run.output) }],
          structuredContent: run.output,
          _meta: { request: run.request, cache: run.cache },
        };
      } catch (error) {
        // A failure is logged here, where it happened, unless the client went away; then it goes back as a result.
        if (!ctx.mcpReq.signal.aborted) {
          logError("tool.failed", error, { tool: definition.name, door: "mcp" });
        }
        return toFailedResult(error);
      }
    },
  );
}

/** Registers the four Open-Meteo tools on an MCP server. */
export function registerTools(
  server: McpServer,
  { openMeteo = createOpenMeteoClient() }: RegisterToolsOptions = {},
): void {
  registerTool(server, OPEN_METEO_TOOLS.geocode_location, openMeteo);
  registerTool(server, OPEN_METEO_TOOLS.get_current_weather, openMeteo);
  registerTool(server, OPEN_METEO_TOOLS.get_forecast, openMeteo);
  registerTool(server, OPEN_METEO_TOOLS.get_air_quality, openMeteo);
}
