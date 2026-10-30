/*
 * hooks/use-lane-status.ts: asks /api/health what works, per lane, for the lane picker's status dots: when the page
 * opens, then every 5 minutes while it's open. Until it answers, each lane is being checked; if its answer can't be
 * read, each is unknown. Nothing else depends on it: a lane can be picked whatever its dot says.
 */
"use client";

import { useEffect, useState } from "react";
import { HEALTH_API_PATH, LANE_STATUS_REFRESH_MS, LIVE_LANE_IDS } from "@/lib/constants";
import type { LaneHealth, LiveLaneId } from "@/lib/types";
import { toLaneHealths } from "@/lib/utils";

// Each lane, while the first answer is on its way.
const CHECKING = Object.fromEntries(LIVE_LANE_IDS.map((laneId) => [laneId, "checking"])) as Record<
  LiveLaneId,
  LaneHealth
>;

/** Each live lane's health, as /api/health last said it; asked again every 5 minutes. */
export function useLaneStatus(): Record<LiveLaneId, LaneHealth> {
  const [healths, setHealths] = useState(CHECKING);
  useEffect(() => {
    const controller = new AbortController();
    const check = () =>
      fetch(HEALTH_API_PATH, { signal: controller.signal })
        // A 503 carries the same answer, saying which lane is down.
        .then((response) => response.json())
        .then((body: unknown) => setHealths(toLaneHealths(body, LIVE_LANE_IDS)))
        .catch(() => {
          if (!controller.signal.aborted) {
            setHealths(toLaneHealths(undefined, LIVE_LANE_IDS));
          }
        });
    // Each ask handles its own failure, so nothing waits on it.
    void check();
    const timer = setInterval(check, LANE_STATUS_REFRESH_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);
  return healths;
}
