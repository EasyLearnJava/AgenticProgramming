/*
 * components/lane-picker.tsx: the 2×2 lane picker: REST or MCP, without or with auth. A lane this deployment can't run
 * is shown, switched off: an auth lane without Apify's token says it needs one; a lane not built yet says which build
 * step makes it live.
 */
import { Fragment, type ReactNode } from "react";
import { LANE_BY_ID, LANE_GRID, LIVE_LANE_IDS } from "@/lib/constants";
import type { LaneId, LiveLaneId } from "@/lib/types";

type LanePickerProps = {
  value: LiveLaneId;
  onChange: (laneId: LiveLaneId) => void;
  availableLaneIds: readonly LiveLaneId[];
};

const ROW_LABELS = ["REST", "MCP"] as const;
const COLUMN_LABELS = ["No auth", "With auth"] as const;

/** What a lane's option says under its name: live, waiting for a token, or the step that makes it live. */
function toLaneState(laneId: LaneId, isAvailable: boolean): string {
  if (isAvailable) {
    return "live";
  }
  return (LIVE_LANE_IDS as readonly LaneId[]).includes(laneId)
    ? "needs an Apify token"
    : `live from step ${LANE_BY_ID[laneId].builtInStep}`;
}

/** Radio buttons laid out as the plan's 2×2; the arrow keys move between the ones this deployment can run. */
export function LanePicker({ value, onChange, availableLaneIds }: LanePickerProps): ReactNode {
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
                    <span className="lane-option-step">{toLaneState(laneId, isAvailable(laneId))}</span>
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
