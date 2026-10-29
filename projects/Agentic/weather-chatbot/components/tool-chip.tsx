/*
 * components/tool-chip.tsx: one tool call: what it asked, through which lane and to which host; opened, the request,
 * the input and the output.
 */
import type { ReactNode } from "react";
import { LANE_BY_ID } from "@/lib/constants";
import type { ToolCallView } from "@/lib/types";
import { toHost, toWireText } from "@/lib/utils";

type ToolChipProps = { call: ToolCallView };

/** Shows a JSON value, or a sentence as it is. */
function toDisplayText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** A tool call as a chip that opens; it's a <details> element, so it works with the keyboard and without script. */
export function ToolChip({ call }: ToolChipProps): ReactNode {
  return (
    <details className="tool-chip">
      <summary>
        <span className="tool-chip-mark" aria-hidden="true">
          ✓
        </span>
        <span className="visually-hidden">Done:</span>
        <code className="tool-chip-name">{call.tool}</code>
        <span className="tool-chip-input">{call.inputSummary}</span>
        <span className="tool-chip-lane">
          {LANE_BY_ID[call.laneId].label} · {toHost(call.wire.url)}
        </span>
      </summary>
      <div className="tool-chip-body">
        <p className="tool-chip-result">→ {call.resultSummary}</p>
        <p className="tool-chip-label">On the wire</p>
        <pre>{toWireText(call.wire)}</pre>
        <p className="tool-chip-label">Input</p>
        <pre>{toDisplayText(call.input)}</pre>
        <p className="tool-chip-label">Output</p>
        <pre>{toDisplayText(call.output)}</pre>
      </div>
    </details>
  );
}
