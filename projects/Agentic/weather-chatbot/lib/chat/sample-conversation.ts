/*
 * lib/chat/sample-conversation.ts: the conversation the chat page shows until the live chat arrives (step 3): the
 * plan's Paris question, with Open-Meteo's real answers from 29 October 2026, and how each lane would send its calls.
 */
import "server-only";
import { LANE_BY_ID, LANE_IDS } from "@/lib/constants";
import type { CompareCell, ForecastView, LaneId, MessageView, ToolCallView, WireRequest } from "@/lib/types";

/** One tool call as one lane would make it: the tool's name and input there, its output, and the request. */
type ViaLane = { tool: string; input: unknown; output: unknown; wire: WireRequest };

const OUR_MCP_URL = "https://<this deployment>/api/mcp";
const ACTOR_TOOL = "gochujang--open-meteo-weather-forecast";
const MCP_HEADERS = { "Content-Type": "application/json", Accept: "application/json, text/event-stream" };
const TOKEN_HEADER = { Authorization: "Bearer <APIFY_TOKEN>" };
const GEOCODE_CALL_ID = 2;
const FORECAST_CALL_ID = 3;

/** An MCP tools/call message, as JSON-RPC text; each call in a session has its own id. */
function toToolsCallBody(id: number, tool: string, input: unknown): string {
  return JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name: tool, arguments: input } });
}

// ① Finding the place. The auth lanes borrow it from the no-auth lane behind the same door: the Actor can't do it.
const GEOCODE_INPUT = { query: "Paris", count: 5 };
const GEOCODE_OUTPUT = {
  candidates: [
    {
      name: "Paris",
      region: "Île-de-France Region",
      country: "FR",
      latitude: 48.85341,
      longitude: 2.3488,
      timeZone: "Europe/Paris",
      population: 2138551,
    },
    {
      name: "Paris",
      region: "Texas",
      country: "US",
      latitude: 33.66094,
      longitude: -95.55551,
      timeZone: "America/Chicago",
      population: 24782,
    },
    {
      name: "Paris",
      region: "Tennessee",
      country: "US",
      latitude: 36.302,
      longitude: -88.32671,
      timeZone: "America/Chicago",
      population: 10150,
    },
    {
      name: "Paris",
      region: "Kentucky",
      country: "US",
      latitude: 38.2098,
      longitude: -84.25299,
      timeZone: "America/New_York",
      population: 9870,
    },
    {
      name: "Paris",
      region: "Illinois",
      country: "US",
      latitude: 39.61115,
      longitude: -87.69614,
      timeZone: "America/Chicago",
      population: 8432,
    },
  ],
  isAmbiguous: false,
};
const GEOCODE_BY_DOOR: Readonly<Record<"rest" | "mcp", ViaLane>> = {
  rest: {
    tool: "geocode_location",
    input: GEOCODE_INPUT,
    output: GEOCODE_OUTPUT,
    wire: {
      method: "GET",
      url: "https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=5&language=en&format=json",
      headers: {},
    },
  },
  mcp: {
    tool: "geocode_location",
    input: GEOCODE_INPUT,
    output: GEOCODE_OUTPUT,
    wire: {
      method: "POST",
      url: OUR_MCP_URL,
      headers: MCP_HEADERS,
      body: toToolsCallBody(GEOCODE_CALL_ID, "geocode_location", GEOCODE_INPUT),
    },
  },
};

// ② The forecast: Open-Meteo for the no-auth pair, the Apify Actor (same input, same token) for the auth pair.
const FORECAST_INPUT = { latitude: 48.85341, longitude: 2.3488, days: 2, includeHourly: true, units: "metric" };
const FORECAST_OUTPUT = {
  timeZone: "Europe/Paris",
  hours: [
    { time: "2026-10-30T12:00", temperature: 12.1, rainChance: 0, weatherCode: 0 },
    { time: "2026-10-30T13:00", temperature: 13.4, rainChance: 0, weatherCode: 1 },
    { time: "2026-10-30T14:00", temperature: 14.6, rainChance: 0, weatherCode: 1 },
    { time: "2026-10-30T15:00", temperature: 15.3, rainChance: 0, weatherCode: 0 },
    { time: "2026-10-30T16:00", temperature: 15.2, rainChance: 0, weatherCode: 0 },
    { time: "2026-10-30T17:00", temperature: 14.4, rainChance: 0, weatherCode: 0 },
  ],
  sunset: "2026-10-30T17:33",
};
const ACTOR_INPUT = {
  locations: [{ name: "Paris", latitude: 48.85341, longitude: 2.3488 }],
  forecastDays: 2,
  mode: "hourly",
};
const ACTOR_OUTPUT = "The Actor's items: their exact shape is recorded in step 0, before this lane is built.";
const FORECAST_BY_LANE: Readonly<Record<LaneId, ViaLane>> = {
  "rest-no-auth": {
    tool: "get_forecast",
    input: FORECAST_INPUT,
    output: FORECAST_OUTPUT,
    wire: {
      method: "GET",
      url: "https://api.open-meteo.com/v1/forecast?latitude=48.85341&longitude=2.3488&hourly=temperature_2m,precipitation_probability,weather_code&daily=sunset&timezone=auto&forecast_days=2",
      headers: {},
    },
  },
  "mcp-no-auth": {
    tool: "get_forecast",
    input: FORECAST_INPUT,
    output: FORECAST_OUTPUT,
    wire: {
      method: "POST",
      url: OUR_MCP_URL,
      headers: MCP_HEADERS,
      body: toToolsCallBody(FORECAST_CALL_ID, "get_forecast", FORECAST_INPUT),
    },
  },
  "rest-auth": {
    tool: ACTOR_TOOL,
    input: ACTOR_INPUT,
    output: ACTOR_OUTPUT,
    wire: {
      method: "POST",
      url: "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items?build=1.0.9&timeout=18&maxTotalChargeUsd=0.01",
      headers: { ...TOKEN_HEADER, "Content-Type": "application/json" },
      body: JSON.stringify(ACTOR_INPUT),
    },
  },
  "mcp-auth": {
    tool: ACTOR_TOOL,
    input: ACTOR_INPUT,
    output: ACTOR_OUTPUT,
    wire: {
      method: "POST",
      url: "https://mcp.apify.com/?tools=gochujang/open-meteo-weather-forecast",
      headers: { ...TOKEN_HEADER, ...MCP_HEADERS },
      body: toToolsCallBody(FORECAST_CALL_ID, ACTOR_TOOL, ACTOR_INPUT),
    },
  },
};

// ③ What the weather card shows: Open-Meteo's real answer for Paris, 30 October 2026, noon to 5 pm.
const PARIS_FORECAST: ForecastView = {
  place: "Paris, Île-de-France, France",
  period: "Friday 30 October, 12:00 to 17:00 Paris time",
  condition: "Clear to mainly clear",
  temperatureRange: "12 to 15 °C",
  sunset: "17:33",
  hourlyRain: ["12:00", "13:00", "14:00", "15:00", "16:00", "17:00"].map((hour) => ({ hour, chancePercent: 0 })),
  fetched: "fetched on 29 October 2026 at 17:00 Paris time",
};

/** One call, as a chip shows it for the chosen lane. */
function toToolCallView(
  id: string,
  laneId: LaneId,
  call: ViaLane,
  inputSummary: string,
  resultSummary: string,
): ToolCallView {
  return { id, laneId, inputSummary, resultSummary, ...call };
}

/** The sample conversation, with its calls going through one lane. */
function toConversation(laneId: LaneId): readonly MessageView[] {
  const geocode = GEOCODE_BY_DOOR[LANE_BY_ID[laneId].transport];
  return [
    { id: "question", role: "user", time: "17:00", text: "Do I need an umbrella in Paris tomorrow afternoon?" },
    {
      id: "answer",
      role: "bot",
      time: "17:00",
      text:
        "No umbrella needed. In Paris (Île-de-France, France), tomorrow, Friday 30 October, the chance of rain is 0% every " +
        "hour from noon to 5 pm, with clear to mainly clear skies and 12 to 15 °C. Sunset is at 17:33.",
      toolCalls: [
        toToolCallView("geocode", laneId, geocode, "“Paris”", "Paris, Île-de-France Region, FR · 48.85, 2.35"),
        toToolCallView(
          "forecast",
          laneId,
          FORECAST_BY_LANE[laneId],
          "48.85, 2.35 · 2 days, hourly",
          "0% rain all afternoon",
        ),
      ],
      forecast: PARIS_FORECAST,
    },
  ];
}

// ④ The conversation for each lane, and the compare view's four cells: the forecast call, through each lane.
export const SAMPLE_MESSAGES_BY_LANE: Readonly<Record<LaneId, readonly MessageView[]>> = {
  "rest-no-auth": toConversation("rest-no-auth"),
  "rest-auth": toConversation("rest-auth"),
  "mcp-no-auth": toConversation("mcp-no-auth"),
  "mcp-auth": toConversation("mcp-auth"),
};

export const SAMPLE_COMPARE_CELLS: readonly CompareCell[] = LANE_IDS.map((laneId) => ({
  lane: LANE_BY_ID[laneId],
  tool: FORECAST_BY_LANE[laneId].tool,
  wire: FORECAST_BY_LANE[laneId].wire,
}));
