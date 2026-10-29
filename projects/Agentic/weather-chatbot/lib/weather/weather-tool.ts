/*
 * lib/weather/weather-tool.ts: the shape every one of our weather tools has. A tool is written once, as a plain
 * object, and run by both no-auth doors: REST inside /api/chat (step 3), MCP inside /api/mcp (step 4).
 */
import "server-only";
import { z } from "zod";
import { MAX_LATITUDE_DEGREES, MAX_LONGITUDE_DEGREES } from "@/lib/constants";
import type { WireRequest } from "@/lib/types";
import type { OpenMeteoClient } from "@/lib/upstream/open-meteo";

/** The input the tools share: a point on the globe, in degrees. */
export const LatitudeSchema = z.number().min(-MAX_LATITUDE_DEGREES).max(MAX_LATITUDE_DEGREES);
export const LongitudeSchema = z.number().min(-MAX_LONGITUDE_DEGREES).max(MAX_LONGITUDE_DEGREES);

/** What a tool needs to run: the Open-Meteo client, and the call's abort signal. */
export type ToolContext = { openMeteo: OpenMeteoClient; signal?: AbortSignal };

/** A tool's answer, and the request to Open-Meteo behind it. */
export type ToolRun<Output> = { output: Output; request: WireRequest; cache: "hit" | "miss" };

/** One weather tool: its name and description for the model, its input schema, how it runs, and its one-line summary. */
export type WeatherTool<Name extends string, Input, Output> = {
  name: Name;
  description: string;
  inputSchema: z.ZodType<Input>;
  run(input: Input, context: ToolContext): Promise<ToolRun<Output>>;
  summarize(output: Output): string;
};
