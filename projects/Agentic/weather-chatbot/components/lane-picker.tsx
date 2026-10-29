/*
 * components/lane-picker.tsx: the 2×2 lane picker: REST or MCP, without or with auth.
 */
import { Fragment, type ReactNode } from "react";
import { LANE_BY_ID, LANE_GRID } from "@/lib/constants";
import type { LaneId } from "@/lib/types";

type LanePickerProps = { value: LaneId; onChange: (laneId: LaneId) => void };

const ROW_LABELS = ["REST", "MCP"] as const;
const COLUMN_LABELS = ["No auth", "With auth"] as const;

/** Radio buttons laid out as the plan's 2×2; the arrow keys move between them. */
export function LanePicker({ value, onChange }: LanePickerProps): ReactNode {
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
                    onChange={() => onChange(laneId)}
                  />
                  <span className="lane-option-text">
                    <span>{lane.label}</span>
                    <span className="lane-option-step">live from step {lane.builtInStep}</span>
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
