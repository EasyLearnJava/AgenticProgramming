/*
 * lib/types.ts: the types the page and the server share: the lanes, the tools' inputs and outputs, and the chat's
 * messages. A tool's Zod schema is declared with its type from here (z.ZodType<ForecastInput>), so the two can't drift.
 */
import type { MCPClient } from "@ai-sdk/mcp";
import type { UIMessage } from "ai";

/** The four lanes: the door (REST or MCP), then the auth. */
export type LaneId = "rest-no-auth" | "rest-auth" | "mcp-no-auth" | "mcp-auth";

/** The lanes built so far: all four, since step 7. An auth lane also needs its token to run. */
export type LiveLaneId = Extract<LaneId, "rest-no-auth" | "mcp-no-auth" | "rest-auth" | "mcp-auth">;

/** What our code uses of an MCP client: listing the tools, calling one, and closing. */
export type McpClient = Pick<MCPClient, "listTools" | "callTool" | "close">;

/** One lane, as the page describes it. */
export type LaneInfo = {
  id: LaneId;
  transport: "rest" | "mcp";
  auth: "none" | "bearer";
  label: string;
  door: string;
  builtInStep: number;
};

/** An HTTP request exactly as it goes out: what a tool chip's wire view shows. */
export type WireRequest = {
  method: "GET" | "POST";
  url: string;
  headers: Readonly<Record<string, string>>;
  body?: string;
};

/** Metric (°C, km/h, mm) or imperial (°F, mph, inches); Open-Meteo converts for us. */
export type Units = "metric" | "imperial";

/** One place, as the Apify Actor takes it: a name for its records, and the coordinates geocoding found. */
export type ActorLocation = { name: string; latitude: number; longitude: number };

/**
 * The auth lanes' forecast input: the Actor's own three fields (one location, 1 to 16 days, daily or hourly), plus the
 * units, which the lane applies itself: the Actor has no such option, and never sees this one.
 */
export type ActorForecastInput = {
  locations: ActorLocation[];
  forecastDays: number;
  mode: "daily" | "hourly";
  units: Units;
};

// ① The tools' inputs, as the model sends them.

export type GeocodeInput = { query: string; count?: number; countryCode?: string };
export type CurrentWeatherInput = { latitude: number; longitude: number; units: Units };
export type ForecastInput = { latitude: number; longitude: number; days: number; includeHourly: boolean; units: Units };
export type AirQualityInput = { latitude: number; longitude: number };

// ② The tools' outputs: what the model reads, and what the page shows. Times are the place's local times.

/** One place geocoding found. Open-Meteo leaves out what it doesn't know, such as a small place's population. */
export type Place = {
  name: string;
  region?: string;
  country?: string;
  countryCode?: string;
  latitude: number;
  longitude: number;
  timeZone?: string;
  population?: number;
};

export type GeocodeResult = { candidates: Place[]; isAmbiguous: boolean };

/** One day of a forecast. A value Open-Meteo doesn't have is null. */
export type ForecastDay = {
  date: string;
  weekday: string;
  condition: string;
  icon: string;
  temperatureMin: number | null;
  temperatureMax: number | null;
  rainChancePercent: number | null;
  sunrise: string | null;
  sunset: string | null;
};

export type ForecastHour = {
  time: string;
  temperature: number | null;
  rainChancePercent: number | null;
  condition: string;
};

export type Forecast = {
  latitude: number;
  longitude: number;
  timeZone: string;
  // The place's own date and time when the tool answered, "2026-10-29T22:00": what now is there.
  localNow: string;
  temperatureUnit: string;
  days: ForecastDay[];
  hours?: ForecastHour[];
  fetchedAt: string;
};

export type CurrentWeather = {
  latitude: number;
  longitude: number;
  timeZone: string;
  observedAt: string;
  temperature: number | null;
  feelsLike: number | null;
  windSpeed: number | null;
  condition: string;
  icon: string;
  isDay: boolean;
  temperatureUnit: string;
  windSpeedUnit: string;
  fetchedAt: string;
};

export type AirQuality = {
  latitude: number;
  longitude: number;
  timeZone: string;
  observedAt: string;
  pm25: number | null;
  pm10: number | null;
  europeanAqi: number | null;
  usAqi: number | null;
  fetchedAt: string;
};

// ③ What each tool call sends the page: the result the model reads, a one-line summary, and how the call went.

/** When an auth lane couldn't answer and its no-auth twin did: which lane failed, and the sentence the chip shows. */
export type LaneFallback = { from: LaneId; sentence: string };

/** How one tool call travelled: the lane, the request, whether the cache answered, and how long it took. */
export type ToolCallRecord = {
  laneId: LaneId;
  wire: WireRequest;
  cache: "hit" | "miss";
  durationMs: number;
};

/** A tool's result, its summary and how the call went; and, when an auth lane fell back, what happened. */
export type ToolResult<Result> = { result: Result; summary: string; call: ToolCallRecord; fallback?: LaneFallback };

/** The four Open-Meteo tools, by name: the input each one takes and the result it gives back. */
export type OpenMeteoToolTypes = {
  geocode_location: { input: GeocodeInput; output: ToolResult<GeocodeResult> };
  get_current_weather: { input: CurrentWeatherInput; output: ToolResult<CurrentWeather> };
  get_forecast: { input: ForecastInput; output: ToolResult<Forecast> };
  get_air_quality: { input: AirQualityInput; output: ToolResult<AirQuality> };
};

/** The auth lanes' forecast tool, under the Apify Actor's name: the same result as get_forecast. */
export type ActorToolTypes = {
  "gochujang--open-meteo-weather-forecast": { input: ActorForecastInput; output: ToolResult<Forecast> };
};

/** Every tool a message can hold. */
export type WeatherToolTypes = OpenMeteoToolTypes & ActorToolTypes;

// ④ The chat's messages: AI SDK's UI messages, with when each was written, and our tools.

/** When a message was written; and, for an answer, whether a time budget cut it short (PLAN.md 9.3). */
export type MessageMetadata = { createdAt: number; isCutShort?: boolean };

export type ChatMessage = UIMessage<MessageMetadata, Record<string, never>, WeatherToolTypes>;

// ⑤ What the page draws.

/** One tool call, as a chip shows it: running, done, failed, or stopped; once done, how the call travelled. */
export type ToolCallView = {
  id: string;
  tool: string;
  status: "running" | "done" | "failed" | "stopped";
  inputSummary: string;
  input: unknown;
  resultSummary?: string;
  errorText?: string;
  output?: unknown;
  call?: ToolCallRecord;
  fallback?: LaneFallback;
};

/** One cell of the compare view: the same call, through one lane. */
export type CompareCell = { lane: LaneInfo; tool: string; wire: WireRequest };

// ⑥ The System design page's diagram: bands, parts, the lines between them, and a legend, in the drawing's units.

/** One of the diagram's four bands, top to bottom. */
export type DiagramBand = { letter: string; title: string; y: number; height: number };

/** A part of the app: where it's drawn, its name, a few short lines about it, and its badge. */
export type DiagramBox = {
  band: string;
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  lines: readonly string[];
  badge?: string;
};

/** How a line between parts reads: a request and its answer, our MCP hop, or a cache. */
export type ArrowKind = "request" | "mcp" | "state";

/** A line between parts, as an SVG path; a trunk that splits into branches has no arrowhead of its own. */
export type DiagramArrow = { path: string; kind: ArrowKind; hasHead: boolean };

/** Words on the drawing, outside the boxes: what a line carries. */
export type DiagramLabel = { x: number; y: number; text: string };

/** The whole diagram, with its title and a description for screen readers. */
export type SystemDiagram = {
  width: number;
  height: number;
  title: string;
  description: string;
  bands: readonly DiagramBand[];
  boxes: readonly DiagramBox[];
  arrows: readonly DiagramArrow[];
  labels: readonly DiagramLabel[];
  legend: { y: number; items: readonly { kind: ArrowKind; text: string }[]; note: string };
};
