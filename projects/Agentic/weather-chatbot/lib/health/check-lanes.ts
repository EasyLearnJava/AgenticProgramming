/*
 * lib/health/check-lanes.ts: the health check (PLAN.md 9.5): each way out of the app, checked as cheaply as it can be,
 * running nothing that costs. Open-Meteo, geocoding London with the cache skipped, so an outage shows; our MCP server,
 * connected and its tool list checked; Apify's REST door, reading the account behind the token; and Apify's MCP server,
 * connected and its tool list checked against our pin. A lane works when every check its answers depend on passes;
 * without Apify's token, the auth lanes are off. Each check has 8 s and logs one health.check line, at its class's
 * level when it fails (an AuthError, at error, reaches Sentry); each run, one health.done line.
 */
import "server-only";
import { HEALTH_CHECK_TIMEOUT_MS, HEALTH_PLACE, LIVE_LANE_IDS } from "@/lib/constants";
import { ContractError, toAppError, UpstreamTimeoutError } from "@/lib/errors";
import { connectToOurMcpServer } from "@/lib/lanes/mcp-no-auth";
import { type Logger, logFailure } from "@/lib/logger";
import type { LiveLaneId } from "@/lib/types";
import { checkApifyToken } from "@/lib/upstream/apify";
import { checkApifyMcp } from "@/lib/upstream/apify-mcp";
import { createOpenMeteoClient, type ResponseCache } from "@/lib/upstream/open-meteo";
import { untilAborted } from "@/lib/utils";

/** The ways out the health check tries, one check each. */
export type CheckName = "open-meteo" | "our-mcp" | "apify-rest" | "apify-mcp";

/** A check: it resolves when its way out works, within the signal; undefined when it's off (no token). */
export type Check = ((signal: AbortSignal) => Promise<void>) | undefined;

/** How a check went: it passed, failed (with its class), or was off; with its time when it ran. */
export type CheckResult = { status: "ok" | "down" | "off"; ms?: number; errorClass?: string };

/** What the health check found: overall, each check, and each lane. */
export type HealthReport = {
  status: "ok" | "down";
  checkedAt: string;
  checks: Record<CheckName, CheckResult>;
  lanes: Record<LiveLaneId, CheckResult["status"]>;
};

/** What checking takes: the logger, the clocks (one to time the checks, one for the report), and each check's time. */
type CheckLanesOptions = { log: Logger; now?: () => number; clock?: () => Date; timeoutMs?: number };

/**
 * What the real checks need: this deployment's origin and the request's id (for our MCP server, as the MCP lanes
 * connect), the bypass secret, Apify's token (without it, the auth lanes are off), the logger, and a stand-in fetch for
 * the tests.
 */
export type HealthCheckOptions = {
  origin: string;
  requestId: string;
  bypassSecret?: string;
  apifyToken?: string;
  log: Logger;
  fetch?: typeof fetch;
};

// The checks each lane's answers depend on: its own door, and Open-Meteo, which every lane geocodes with (the auth
// lanes too, and MCP · with auth through our MCP server).
const CHECKS_BY_LANE: Readonly<Record<LiveLaneId, readonly CheckName[]>> = {
  "rest-no-auth": ["open-meteo"],
  "mcp-no-auth": ["our-mcp", "open-meteo"],
  "rest-auth": ["apify-rest", "open-meteo"],
  "mcp-auth": ["apify-mcp", "our-mcp", "open-meteo"],
};

// A cache that never answers and keeps nothing: the check asks Open-Meteo itself, so an outage shows.
const NO_CACHE: ResponseCache = { get: async () => undefined, set: async () => undefined };

/** One check, within its time: how it went, and one health.check line; a failure at its class's level. */
async function runCheck(
  name: CheckName,
  check: Check,
  { log, now, timeoutMs }: Required<Pick<CheckLanesOptions, "log" | "now" | "timeoutMs">>,
): Promise<CheckResult> {
  if (check === undefined) {
    return { status: "off" };
  }
  const startedAt = now();
  const signal = AbortSignal.timeout(timeoutMs);
  try {
    await untilAborted(check(signal), signal);
    const ms = Math.round(now() - startedAt);
    log.info({ event: "health.check", check: name, status: "ok", ms });
    return { status: "ok", ms };
  } catch (error) {
    const ms = Math.round(now() - startedAt);
    const failure = signal.aborted
      ? new UpstreamTimeoutError(`The ${name} check didn't pass within ${timeoutMs} ms.`, { cause: error })
      : toAppError(error);
    logFailure(log, "health.check", failure, { check: name, ms });
    return { status: "down", ms, errorClass: failure.name };
  }
}

/** A lane's status: off when a check it needs is off, down when one failed, else ok. */
function toLaneStatus(laneId: LiveLaneId, checks: Record<CheckName, CheckResult>): CheckResult["status"] {
  const statuses = CHECKS_BY_LANE[laneId].map((name) => checks[name].status);
  if (statuses.includes("off")) {
    return "off";
  }
  return statuses.includes("down") ? "down" : "ok";
}

/** Runs every check at once, each within its time, and says what works: overall, per check, and per lane. */
export async function checkLanes(
  checks: Readonly<Record<CheckName, Check>>,
  {
    log,
    now = performance.now.bind(performance),
    clock = () => new Date(),
    timeoutMs = HEALTH_CHECK_TIMEOUT_MS,
  }: CheckLanesOptions,
): Promise<HealthReport> {
  const startedAt = now();
  const names = Object.keys(checks) as CheckName[];
  const results = await Promise.all(names.map((name) => runCheck(name, checks[name], { log, now, timeoutMs })));
  const byName = Object.fromEntries(names.map((name, index) => [name, results[index]])) as Record<
    CheckName,
    CheckResult
  >;
  const lanes = Object.fromEntries(LIVE_LANE_IDS.map((laneId) => [laneId, toLaneStatus(laneId, byName)])) as Record<
    LiveLaneId,
    CheckResult["status"]
  >;
  const status = Object.values(lanes).includes("down") ? "down" : "ok";
  log.info({ event: "health.done", status, ms: Math.round(now() - startedAt), lanes });
  return { status, checkedAt: clock().toISOString(), checks: byName, lanes };
}

/** The four checks, against the real services: none runs an Actor, so none costs. */
export function createHealthChecks({
  origin,
  requestId,
  bypassSecret,
  apifyToken,
  log,
  fetch: fetchAll = fetch,
}: HealthCheckOptions): Record<CheckName, Check> {
  return {
    "open-meteo": async (signal) => {
      const openMeteo = createOpenMeteoClient({ fetch: fetchAll, cache: NO_CACHE });
      const { data } = await openMeteo.searchPlaces({ query: HEALTH_PLACE, count: 1 }, { signal, log });
      if (data.length === 0) {
        throw new ContractError(`Open-Meteo found no ${HEALTH_PLACE}.`);
      }
    },
    "our-mcp": async (signal) => {
      const connection = await connectToOurMcpServer({ origin, requestId, log, bypassSecret, signal, fetch: fetchAll });
      await connection.close();
    },
    "apify-rest":
      apifyToken === undefined
        ? undefined
        : (signal) => checkApifyToken({ token: apifyToken, fetch: fetchAll, signal, log }),
    "apify-mcp":
      apifyToken === undefined
        ? undefined
        : (signal) => checkApifyMcp({ token: apifyToken, fetch: fetchAll, signal, log }),
  };
}
