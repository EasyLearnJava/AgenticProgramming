/*
 * lib/lanes/open-lane.ts: opens the lane the user picked. Each build step adds the lane it makes live; the auth lanes
 * will come with their fallback to the no-auth lane behind the same door (steps 6 and 7).
 */
import "server-only";
import type { Lane } from "@/lib/lanes/lane";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import type { LiveLaneId } from "@/lib/types";

const OPEN_BY_LANE: Readonly<Record<LiveLaneId, () => Lane>> = {
  "rest-no-auth": () => openRestNoAuthLane(),
};

/** Opens a live lane, ready for the model to use its tools. */
export function openLane(laneId: LiveLaneId): Lane {
  return OPEN_BY_LANE[laneId]();
}
