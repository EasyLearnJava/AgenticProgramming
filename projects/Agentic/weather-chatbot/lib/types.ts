/*
 * lib/types.ts: the types the page and the server share: the lanes, the tools' inputs and outputs, and the chat's
 * messages. A tool's Zod schema is declared with its type from here (z.ZodType<ForecastInput>), so the two can't drift.
 */
import type { UIMessage } from "ai";

/** The four lanes: the door (REST or MCP), then the auth. */
export type LaneId = "rest-no-auth" | "rest-auth" | "mcp-no-auth" | "mcp-auth";

/** The lanes that answer for real so far; each build step adds the lane it makes live. */
export type LiveLaneId = Extract<LaneId, "rest-no-auth">;

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

/** How one tool call travelled: the lane, the request, whether the cache answered, and how long it took. */
export type ToolCallRecord = {
  laneId: LaneId;
  wire: WireRequest;
  cache: "hit" | "miss";
  durationMs: number;
};

export type ToolResult<Result> = { result: Result; summary: string; call: ToolCallRecord };

/** The four weather tools, by name: the input each one takes and the result it gives back. */
export type WeatherToolTypes = {
  geocode_location: { input: GeocodeInput; output: ToolResult<GeocodeResult> };
  get_current_weather: { input: CurrentWeatherInput; output: ToolResult<CurrentWeather> };
  get_forecast: { input: ForecastInput; output: ToolResult<Forecast> };
  get_air_quality: { input: AirQualityInput; output: ToolResult<AirQuality> };
};

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
};

/** One cell of the compare view: the same call, through one lane. */
export type CompareCell = { lane: LaneInfo; tool: string; wire: WireRequest };
