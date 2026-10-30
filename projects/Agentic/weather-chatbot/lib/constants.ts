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

// ③ The lanes built so far, and the one a new chat starts on: MCP · no auth (PLAN.md 4.5). An auth lane also needs
// Apify's token on the deployment, or it waits.
export const LIVE_LANE_IDS: readonly LiveLaneId[] = ["rest-no-auth", "mcp-no-auth", "rest-auth", "mcp-auth"];
export const TOKEN_LANE_IDS: readonly LiveLaneId[] = ["rest-auth", "mcp-auth"];
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
// Connecting to our MCP server, on either MCP lane: the handshake and the tool list, before the model starts. 6 s: a
// cold start slowed by Sentry didn't connect within 3 s live, and took up to 3.9 s on a laptop (bug story 18).
export const MCP_CONNECT_TIMEOUT_MS = 6000;
// An Actor run on an auth lane takes seconds, not milliseconds: it gets 20 s (25 on MCP · with auth, which may connect
// first: APIFY_MCP_ACTOR_BUDGET_MS), then its tool's budget leaves the fallback a tool's usual 8 s.
export const AUTH_TOOL_TIMEOUT_MS = 20_000;
// A fallback starts only with this much of the answer's budget left: the twin's 8 s, and time to write the answer.
export const FALLBACK_MIN_LEFT_MS = 12_000;
// BotID's check of the chat's caller (step 8): past this, the request goes on without its verdict.
export const BOTID_TIMEOUT_MS = 3000;

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

// ⑬ Request ids (PLAN.md 9.1): Vercel's own id for a request, and the header that carries ours on to /api/mcp and back
// to the page. In a log line, a failure's cause is cut to 300 characters, and a bug's stack to its first 8 lines.
export const VERCEL_ID_HEADER = "x-vercel-id";
export const REQUEST_ID_HEADER = "x-request-id";
export const MAX_LOGGED_CAUSE_CHARS = 300;
export const MAX_LOGGED_STACK_LINES = 8;

// ⑭ The Apify Actor behind the auth lanes (PLAN.md 4.3): its run-sync address, pinned to build 1.0.9, stopped by
// Apify at 18 s (before our 20 s budget) and at a charge of $0.01; and its tool's name, as Apify's MCP server gives it.
export const APIFY_ACTOR_RUN_URL =
  "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items";
export const APIFY_ACTOR_BUILD = "1.0.9";
export const APIFY_RUN_TIMEOUT_SECONDS = 18;
export const APIFY_MAX_CHARGE_USD = 0.01;
export const ACTOR_TOOL_NAME = "gochujang--open-meteo-weather-forecast";
// The same Actor through Apify's MCP server (step 7): the address that lists call-actor, which runs it with the REST
// door's limits, and the Actor's own tool, for our pin, with their helpers; the Actor, as call-actor names it; the
// helper that reads a run's items, at most this many in one read (an hourly forecast has 72); how long connecting may
// take, the server being Apify's, across the internet; and the Actor call's own time there, the run's 20 s plus that.
export const APIFY_MCP_URL = "https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast";
export const APIFY_RUN_TOOL = "call-actor";
export const APIFY_ACTOR = "gochujang/open-meteo-weather-forecast";
export const APIFY_DATASET_TOOL = "get-dataset-items";
export const MAX_ACTOR_ITEMS = 100;
export const APIFY_MCP_CONNECT_TIMEOUT_MS = 5000;
export const APIFY_MCP_ACTOR_BUDGET_MS = AUTH_TOOL_TIMEOUT_MS + APIFY_MCP_CONNECT_TIMEOUT_MS;
// How long closing Apify's session may hold up the answer's end: AI SDK ends a 2025 session with a DELETE that has no
// time limit of its own.
export const APIFY_MCP_CLOSE_TIMEOUT_MS = 1000;
// Apify's own words about a failed run are cut to this many characters before they go in our message.
export const MAX_APIFY_DETAIL_CHARS = 200;

// Where the log lines go (step 9): Axiom's US deployment, whose ingest takes a batch of lines a request; each batch has
// 2 s, and at most 1,000 lines wait between batches. Sentry has the same 2 s to send the errors it holds.
export const AXIOM_INGEST_HOST = "us-east-1.aws.edge.axiom.co";
export const AXIOM_FLUSH_TIMEOUT_MS = 2000;
export const AXIOM_MAX_PENDING_LINES = 1000;
export const SENTRY_FLUSH_TIMEOUT_MS = 2000;
