/*
 * lib/lanes/open-lane.ts: opens the lane the user picked. Each build step adds the lane it makes live; the auth lanes
 * will come with their fallback to the no-auth lane behind the same door (steps 6 and 7).
 */
import "server-only";
import { type Config, config } from "@/lib/config";
import type { Lane } from "@/lib/lanes/lane";
import { openMcpNoAuthLane } from "@/lib/lanes/mcp-no-auth";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import type { LiveLaneId } from "@/lib/types";

/** What opening a lane needs: the chat request's address (to find this deployment's /api/mcp), and its signal. */
export type OpenLaneOptions = { requestUrl: string; signal: AbortSignal };

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

const OPEN_BY_LANE: Readonly<Record<LiveLaneId, (options: OpenLaneOptions) => Promise<Lane>>> = {
  "rest-no-auth": async () => openRestNoAuthLane(),
  "mcp-no-auth": ({ requestUrl, signal }) =>
    openMcpNoAuthLane({
      origin: toSelfOrigin(requestUrl, config.deployment),
      signal,
      bypassSecret: config.mcp.bypassSecret,
    }),
};

/** Opens a live lane, ready for the model to use its tools. */
export function openLane(laneId: LiveLaneId, options: OpenLaneOptions): Promise<Lane> {
  return OPEN_BY_LANE[laneId](options);
}
