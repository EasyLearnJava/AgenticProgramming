/*
 * lib/lanes/open-lane.ts: opens the lane the user picked. Each build step adds the lane it makes live; an auth lane
 * opens only with Apify's token, and falls back to the no-auth lane behind the same door (steps 6 and 7).
 */
import "server-only";
import { type Config, config } from "@/lib/config";
import { LIVE_LANE_IDS, TOKEN_LANE_IDS } from "@/lib/constants";
import { ConfigError } from "@/lib/errors";
import type { Lane } from "@/lib/lanes/lane";
import { openMcpNoAuthLane } from "@/lib/lanes/mcp-no-auth";
import { openRestAuthLane } from "@/lib/lanes/rest-auth";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import type { Logger } from "@/lib/logger";
import type { LiveLaneId } from "@/lib/types";

/**
 * What opening a lane needs: the chat request's address (to find this deployment's /api/mcp), its signal, its id
 * (which the MCP lane passes on to /api/mcp), and its logger.
 */
export type OpenLaneOptions = { requestUrl: string; signal: AbortSignal; requestId: string; log: Logger };

/**
 * This deployment's own origin, for the MCP lane's call to /api/mcp. On Vercel it's the address the chat request came
 * to, if that's one of the deployment's own (its URL, its branch's, the production domain); otherwise the deployment's
 * own URL, so a forged Host header can't send the call, or the bypass secret, anywhere else. Off Vercel (a laptop),
 * it's the request's own origin.
 */
export function toSelfOrigin(requestUrl: string, deployment: Config["deployment"]): string {
  const { origin, host } = new URL(requestUrl);
  if (deployment.url === undefined) {
    return origin;
  }
  return deployment.hosts.includes(host) ? `https://${host}` : `https://${deployment.url}`;
}

/** The lanes this deployment can run: every lane built so far, an auth lane only when Apify's token is set. */
export function toAvailableLaneIds(apifyToken: string | undefined): LiveLaneId[] {
  return LIVE_LANE_IDS.filter((laneId) => apifyToken !== undefined || !TOKEN_LANE_IDS.includes(laneId));
}

const OPEN_BY_LANE: Readonly<Record<LiveLaneId, (options: OpenLaneOptions) => Promise<Lane>>> = {
  "rest-no-auth": async ({ log }) => openRestNoAuthLane({ log }),
  "rest-auth": async ({ log, requestId }) => {
    // The page offers this lane only when the token is set, and the request's rules refuse it without one; this is
    // the last guard.
    const token = config.apify.token;
    if (token === undefined) {
      throw new ConfigError("APIFY_TOKEN isn't set, so REST · with auth can't run.");
    }
    return openRestAuthLane({ token, requestId, log });
  },
  "mcp-no-auth": ({ requestUrl, signal, requestId, log }) =>
    openMcpNoAuthLane({
      origin: toSelfOrigin(requestUrl, config.deployment),
      requestId,
      log,
      signal,
      bypassSecret: config.mcp.bypassSecret,
    }),
};

/** Opens a live lane, ready for the model to use its tools. */
export function openLane(laneId: LiveLaneId, options: OpenLaneOptions): Promise<Lane> {
  return OPEN_BY_LANE[laneId](options);
}
