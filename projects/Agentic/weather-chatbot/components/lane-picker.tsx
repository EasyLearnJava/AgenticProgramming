/*
 * components/lane-picker.tsx: the 2×2 lane picker: REST or MCP, without or with auth. A lane this deployment runs shows
 * its health, from /api/health (step 9): a dot, and words that say the same. A lane it can't run is shown, switched
 * off: an auth lane without Apify's token says it needs one; a lane not built yet says which build step makes it live.
 */
import { Fragment, type ReactNode } from "react";
import { LANE_BY_ID, LANE_GRID, LIVE_LANE_IDS } from "@/lib/constants";
import type { LaneHealth, LaneId, LiveLaneId } from "@/lib/types";

type LanePickerProps = {
  value: LiveLaneId;
  onChange: (laneId: LiveLaneId) => void;
  availableLaneIds: readonly LiveLaneId[];
  healths: Readonly<Record<LiveLaneId, LaneHealth>>;
};

// A lane's health in words, beside its dot: the words say it, not the colour alone.
const HEALTH_WORDS: Readonly<Record<LaneHealth, string>> = {
  checking: "checking…",
  ok: "working",
  down: "not answering",
  off: "switched off",
  unknown: "status unknown",
};

const ROW_LABELS = ["REST", "MCP"] as const;
const COLUMN_LABELS = ["No auth", "With auth"] as const;

/**
 * What a lane's option says under its name: a lane this deployment runs, its health, beside its dot; else that it
 * needs a token, or the step that makes it live.
 */
function toLaneState(laneId: LaneId, health: LaneHealth | undefined): { words: string; dot?: LaneHealth } {
  if (health !== undefined) {
    return { words: HEALTH_WORDS[health], dot: health };
  }
  return (LIVE_LANE_IDS as readonly LaneId[]).includes(laneId)
    ? { words: "needs an Apify token" }
    : { words: `live from step ${LANE_BY_ID[laneId].builtInStep}` };
}

/** Radio buttons laid out as the plan's 2×2; the arrow keys move between the ones this deployment can run. */
export function LanePicker({ value, onChange, availableLaneIds, healths }: LanePickerProps): ReactNode {
  const isAvailable = (laneId: LaneId): laneId is LiveLaneId =>
    (availableLaneIds as readonly LaneId[]).includes(laneId);
  return (
    <fieldset className="lane-picker">
      <legend>Lane: how the bot reaches the weather</legend>
      <div className="lane-grid">
        <span aria-hidden="true" />
        {COLUMN_LABELS.map((label) => (
          <span key={label} className="lane-grid-head" aria-hidden="true">
            {label}
          </span>
        ))}
        {LANE_GRID.map((row, rowIndex) => (
          <Fragment key={ROW_LABELS[rowIndex]}>
            <span className="lane-grid-head" aria-hidden="true">
              {ROW_LABELS[rowIndex]}
            </span>
            {row.map((laneId) => {
              const lane = LANE_BY_ID[laneId];
              const state = toLaneState(laneId, isAvailable(laneId) ? healths[laneId] : undefined);
              return (
                <label key={laneId} className="lane-option">
                  <input
                    type="radio"
                    name="lane"
                    value={laneId}
                    checked={value === laneId}
                    disabled={!isAvailable(laneId)}
                    onChange={() => (isAvailable(laneId) ? onChange(laneId) : undefined)}
                  />
                  <span className="lane-option-text">
                    <span>{lane.label}</span>
                    <span className="lane-option-step">
                      {state.dot === undefined ? null : (
                        <span className={`lane-dot lane-dot-${state.dot}`} aria-hidden="true" />
                      )}
                      {state.words}
                    </span>
                  </span>
                </label>
              );
            })}
          </Fragment>
        ))}
      </div>
    </fieldset>
  );
}
