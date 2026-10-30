/*
 * app/api/health/route.ts: GET /api/health, the health check (step 9): what works, per lane, for the lane picker's
 * status dots and an outside uptime monitor. 200 when every lane that's on works, 503 when one doesn't. Each copy of
 * the function runs the checks at most once a minute for each address it's asked on, and Vercel's CDN keeps a 200 for
 * a minute, so repeat requests stop at the edge; a 503 is never kept. Its lines go to Axiom, and an error to Sentry.
 */
import { waitUntil } from "@vercel/functions";
import { config } from "@/lib/config";
import { HEALTH_API_PATH, HEALTH_CDN_MAX_AGE_SECONDS, HEALTH_RESULT_TTL_MS, VERCEL_ID_HEADER } from "@/lib/constants";
import { checkLanes, createHealthChecks, type HealthReport } from "@/lib/health/check-lanes";
import { toSelfOrigin } from "@/lib/lanes/open-lane";
import { flushLogs, logger } from "@/lib/logger";
import { markTrace } from "@/lib/sentry";
import { toRequestId } from "@/lib/utils";

// The checks run at once, 8 s each at most; then the lines go out, within 2 s.
export const maxDuration = 20;

const HTTP_OK = 200;
const HTTP_UNAVAILABLE = 503;
// A 200 for browsers to ask again each time, and for Vercel's CDN to keep a minute; a 503, for nobody to keep.
const WORKING_CACHE_CONTROL = `public, max-age=0, s-maxage=${HEALTH_CDN_MAX_AGE_SECONDS}`;
const DOWN_CACHE_CONTROL = "no-store";

// This copy's latest run for each address: the requests to that address within a minute of the run's start get its
// result, waiting if need be. One address's run never answers for another's: our MCP server, reached through a
// deployment's own protected address, refuses the check (Vercel's 401) where the live site's works (bug story 19).
// toSelfOrigin keeps to the deployment's own addresses: on Vercel, three at most.
const latestByOrigin = new Map<string, { startedAt: number; report: Promise<HealthReport> }>();

/** This address's latest result if its run started less than a minute ago; else a new run, sent out when it's done. */
function toReport(request: Request): Promise<HealthReport> {
  const now = Date.now();
  const origin = toSelfOrigin(request.url, config.deployment);
  const latest = latestByOrigin.get(origin);
  if (latest !== undefined && now - latest.startedAt < HEALTH_RESULT_TTL_MS) {
    return latest.report;
  }
  const requestId = toRequestId(request.headers.get(VERCEL_ID_HEADER));
  const log = logger.child({ requestId, route: HEALTH_API_PATH, origin });
  markTrace(requestId);
  const checks = createHealthChecks({
    origin,
    requestId,
    bypassSecret: config.mcp.bypassSecret,
    apifyToken: config.apify.token,
    log,
  });
  const report = checkLanes(checks, { log });
  latestByOrigin.set(origin, { startedAt: now, report });
  waitUntil(report.then(flushLogs));
  return report;
}

/** What works, per lane, as JSON: 200 when every lane that's on works, kept a minute at the edge; else 503, never. */
export async function GET(request: Request): Promise<Response> {
  const report = await toReport(request);
  const isWorking = report.status === "ok";
  return Response.json(report, {
    status: isWorking ? HTTP_OK : HTTP_UNAVAILABLE,
    headers: { "cache-control": isWorking ? WORKING_CACHE_CONTROL : DOWN_CACHE_CONTROL },
  });
}
