/*
 * lib/constants.ts: every fixed value the app uses, by name: the lanes, the chat's limits, the time budgets, the cache
 * times and Open-Meteo's addresses. Each name ends with its unit.
 */
import type { LaneId, LaneInfo, LiveLaneId } from "@/lib/types";

// ① The four lanes: which door, which auth, where the call goes, and the build step that makes each one live.
export const LANE_BY_ID: Readonly<Record<LaneId, LaneInfo>> = {
  "rest-no-auth": {
    id: "rest-no-auth",
    transport: "rest",
    auth: "none",
    label: "REST · no auth",
    door: "api.open-meteo.com",
    builtInStep: 3,
  },
  "rest-auth": {
    id: "rest-auth",
    transport: "rest",
    auth: "bearer",
    label: "REST · with auth",
    door: "api.apify.com",
    builtInStep: 6,
  },
  "mcp-no-auth": {
    id: "mcp-no-auth",
    transport: "mcp",
    auth: "none",
    label: "MCP · no auth",
    door: "/api/mcp, our MCP server",
    builtInStep: 4,
  },
  "mcp-auth": {
    id: "mcp-auth",
    transport: "mcp",
    auth: "bearer",
    label: "MCP · with auth",
    door: "mcp.apify.com",
    builtInStep: 7,
  },
};

// ② The 2×2 picker, row by row: REST, then MCP; without auth, then with it.
export const LANE_GRID: readonly (readonly [LaneId, LaneId])[] = [
  ["rest-no-auth", "rest-auth"],
  ["mcp-no-auth", "mcp-auth"],
];

export const LANE_IDS: readonly LaneId[] = LANE_GRID.flat();

// ③ The lanes that answer for real, and the one a new chat starts on: MCP · no auth (PLAN.md 4.5).
export const LIVE_LANE_IDS: readonly LiveLaneId[] = ["rest-no-auth", "mcp-no-auth"];
export const DEFAULT_LANE_ID: LiveLaneId = "mcp-no-auth";

// ④ What one chat request may carry (PLAN.md 9.2, InputError): messages, each of yours, and the whole history.
export const MAX_MESSAGES = 20;
export const MAX_MESSAGE_CHARS = 2000;
export const MAX_HISTORY_CHARS = 200_000;

// ⑤ One answer: at most 5 steps (model calls), and a cap on what the model writes.
export const MAX_STEPS = 5;
export const MAX_OUTPUT_TOKENS = 2000;

// ⑥ The time budgets (PLAN.md 9.3): the whole answer, the model's first chunk, and a tool call on a no-auth lane.
export const ANSWER_TIMEOUT_MS = 50_000;
export const FIRST_CHUNK_TIMEOUT_MS = 10_000;
export const TOOL_TIMEOUT_MS = 8000;
// Connecting to an MCP lane: the handshake and the tool list, before the model starts.
export const MCP_CONNECT_TIMEOUT_MS = 3000;

// ⑦ Each call to Open-Meteo: 3 s a try, two tries, a short random wait between; a 429 is retried only when its
// Retry-After fits in the tool's budget.
export const OPEN_METEO_TRY_TIMEOUT_MS = 3000;
export const OPEN_METEO_TRIES = 2;
export const RETRY_WAIT_MAX_MS = 500;
export const RETRY_AFTER_MAX_MS = 1500;

// ⑧ How long Open-Meteo's answers stay in the Runtime Cache (PLAN.md 7.6): 30 days, 10 minutes, 30 minutes.
export const GEOCODE_CACHE_TTL_SECONDS = 2_592_000;
export const CURRENT_WEATHER_CACHE_TTL_SECONDS = 600;
export const FORECAST_CACHE_TTL_SECONDS = 1800;
export const AIR_QUALITY_CACHE_TTL_SECONDS = 1800;

// ⑨ The tools' limits: places per search, forecast days, the days an hourly forecast covers, and coordinates.
export const DEFAULT_PLACE_COUNT = 5;
export const MAX_PLACE_COUNT = 10;
export const MAX_QUERY_CHARS = 100;
export const MAX_FORECAST_DAYS = 16;
export const MAX_HOURLY_DAYS = 3;
export const COORDINATE_DECIMALS = 2;
export const MAX_LATITUDE_DEGREES = 90;
export const MAX_LONGITUDE_DEGREES = 180;

// ⑩ Open-Meteo's three APIs (PLAN.md 7.6).
export const OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search";
export const OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
export const OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality";

// ⑪ The app's own addresses: the chat, and the nearby city for a suggested question. The chat marks its own error
// responses with a header, so the page can tell them from Vercel's.
export const CHAT_API_PATH = "/api/chat";
export const NEARBY_CITY_API_PATH = "/api/nearby-city";
// Our MCP server (MCP · no auth's door), the largest message it takes, and the name and version it gives MCP clients.
export const MCP_API_PATH = "/api/mcp";
export const MAX_MCP_BODY_BYTES = 8192;
export const MCP_SERVER_INFO = { name: "nimbus-weather", version: "1.0.0" } as const;
export const OWN_ERROR_HEADER = "x-nimbus-error";

// ⑫ "Use my location": a position the browser found in the last 10 minutes will do; give up after 10 s.
export const LOCATION_MAX_AGE_MS = 600_000;
export const LOCATION_TIMEOUT_MS = 10_000;
