/*
 * tests/e2e/chat-stream.ts: an answer to the Paris question, as /api/chat streams it (AI SDK's UI message stream,
 * typed by AI SDK's own chunk type), with Open-Meteo's real numbers from 29 October 2026. The end-to-end tests answer
 * the page's /api/chat with it, so they test the page without calling a model.
 */
import type { UIMessageChunk } from "ai";
import type { Forecast, GeocodeResult, MessageMetadata, ToolResult, WireRequest } from "@/lib/types";

const CREATED_AT = Date.parse("2026-10-29T16:00:00Z");
const GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=5&language=en&format=json";
export const FORECAST_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35" +
  "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset" +
  "&hourly=temperature_2m,precipitation_probability,weather_code&timezone=auto&forecast_days=2";
export const ANSWER =
  "No umbrella needed. In Paris (Île-de-France, France), tomorrow, Friday 30 October, the chance of rain is 0% " +
  "every hour from noon to 5 pm, with clear skies and 12 to 15 °C.";

const GEOCODE_OUTPUT: ToolResult<GeocodeResult> = {
  result: {
    candidates: [
      {
        name: "Paris",
        region: "Île-de-France Region",
        country: "France",
        countryCode: "FR",
        latitude: 48.85341,
        longitude: 2.3488,
        timeZone: "Europe/Paris",
        population: 2138551,
      },
    ],
    isAmbiguous: false,
  },
  summary: "Paris, Île-de-France Region, FR · 48.85, 2.35",
  call: {
    laneId: "rest-no-auth",
    wire: { method: "GET", url: GEOCODE_URL, headers: { accept: "application/json" } },
    cache: "miss",
    durationMs: 287,
  },
};

const FORECAST_OUTPUT: ToolResult<Forecast> = {
  result: {
    latitude: 48.85,
    longitude: 2.35,
    timeZone: "Europe/Paris",
    temperatureUnit: "°C",
    days: [
      {
        date: "2026-10-29",
        weekday: "Thursday",
        condition: "Fog",
        icon: "🌫️",
        temperatureMin: 5.6,
        temperatureMax: 15.6,
        rainChancePercent: 0,
        sunrise: "2026-10-29T07:32",
        sunset: "2026-10-29T17:35",
      },
      {
        date: "2026-10-30",
        weekday: "Friday",
        condition: "Mainly clear",
        icon: "🌤️",
        temperatureMin: 6.1,
        temperatureMax: 15.3,
        rainChancePercent: 0,
        sunrise: "2026-10-30T07:34",
        sunset: "2026-10-30T17:33",
      },
    ],
    fetchedAt: "2026-10-29T16:00:00.000Z",
  },
  summary: "2 days, hourly · 6 to 16 °C · rain up to 0%",
  call: {
    laneId: "rest-no-auth",
    wire: { method: "GET", url: FORECAST_URL, headers: { accept: "application/json" } },
    cache: "miss",
    durationMs: 412,
  },
};

const METADATA: MessageMetadata = { createdAt: CREATED_AT };

// The same answer through MCP · no auth: each call a JSON-RPC tools/call to our MCP server, as AI SDK's MCP client
// sends it (MCP 2026-07-28), recorded by the lane.
export const MCP_URL = "https://weather-chatbot-hazel.vercel.app/api/mcp";

/** A tools/call to our MCP server, as the MCP lane records it. */
function toMcpWire(tool: string, input: unknown, id: number): WireRequest {
  return {
    method: "POST",
    url: MCP_URL,
    headers: {
      accept: "application/json, text/event-stream",
      "content-type": "application/json",
      "mcp-method": "tools/call",
      "mcp-name": tool,
      "mcp-protocol-version": "2026-07-28",
      "user-agent": "ai-sdk/2.0.86 node.js/22",
    },
    body: JSON.stringify({ method: "tools/call", params: { name: tool, arguments: input }, jsonrpc: "2.0", id }),
  };
}

const MCP_GEOCODE_OUTPUT: ToolResult<GeocodeResult> = {
  ...GEOCODE_OUTPUT,
  call: {
    laneId: "mcp-no-auth",
    wire: toMcpWire("geocode_location", { query: "Paris" }, 2),
    cache: "miss",
    durationMs: 612,
  },
};

const MCP_FORECAST_INPUT = { latitude: 48.85341, longitude: 2.3488, days: 2, includeHourly: true, units: "metric" };

const MCP_FORECAST_OUTPUT: ToolResult<Forecast> = {
  ...FORECAST_OUTPUT,
  call: {
    laneId: "mcp-no-auth",
    wire: toMcpWire("get_forecast", MCP_FORECAST_INPUT, 3),
    cache: "hit",
    durationMs: 143,
  },
};

const PARIS_CHUNKS: UIMessageChunk[] = [
  { type: "start", messageId: "answer-1", messageMetadata: METADATA },
  { type: "start-step" },
  { type: "tool-input-available", toolCallId: "call-1", toolName: "geocode_location", input: { query: "Paris" } },
  { type: "tool-output-available", toolCallId: "call-1", output: GEOCODE_OUTPUT },
  { type: "finish-step" },
  { type: "start-step" },
  {
    type: "tool-input-available",
    toolCallId: "call-2",
    toolName: "get_forecast",
    input: { latitude: 48.85341, longitude: 2.3488, days: 2, includeHourly: true, units: "metric" },
  },
  { type: "tool-output-available", toolCallId: "call-2", output: FORECAST_OUTPUT },
  { type: "finish-step" },
  { type: "start-step" },
  { type: "text-start", id: "text-1" },
  { type: "text-delta", id: "text-1", delta: ANSWER },
  { type: "text-end", id: "text-1" },
  { type: "finish-step" },
  { type: "finish", messageMetadata: METADATA },
];

// An answer a time budget cut short: the geocoding call started, then the server stopped the answer.
const CUT_SHORT_CHUNKS: UIMessageChunk[] = [
  { type: "start", messageId: "answer-2", messageMetadata: METADATA },
  { type: "start-step" },
  { type: "tool-input-available", toolCallId: "call-9", toolName: "geocode_location", input: { query: "Paris" } },
  { type: "message-metadata", messageMetadata: { ...METADATA, isCutShort: true } },
  { type: "abort", reason: "TimeoutError: First chunk timeout of 10000ms exceeded" },
];

/** Chunks as an HTTP response body: one `data:` line per chunk, then `[DONE]`. */
function toStreamBody(chunks: readonly UIMessageChunk[]): string {
  return `${chunks.map((chunk) => `data: ${JSON.stringify(chunk)}\n\n`).join("")}data: [DONE]\n\n`;
}

// The Paris answer through MCP · no auth: the same chunks, with the MCP lane's records.
const MCP_PARIS_CHUNKS: UIMessageChunk[] = PARIS_CHUNKS.map((chunk) => {
  if (chunk.type !== "tool-output-available") {
    return chunk;
  }
  return { ...chunk, output: chunk.toolCallId === "call-1" ? MCP_GEOCODE_OUTPUT : MCP_FORECAST_OUTPUT };
});

/** The Paris answer (REST · no auth, then MCP · no auth), and an answer a time budget cut short, as /api/chat sends them. */
export const PARIS_STREAM_BODY = toStreamBody(PARIS_CHUNKS);
export const MCP_PARIS_STREAM_BODY = toStreamBody(MCP_PARIS_CHUNKS);
export const CUT_SHORT_STREAM_BODY = toStreamBody(CUT_SHORT_CHUNKS);

/** The headers /api/chat sends with a stream. */
export const STREAM_HEADERS = { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" };
