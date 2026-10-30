/*
 * components/tool-chip.tsx: one tool call: what it asked and how it's going; once done, the lane, the host and the
 * time, and, when an auth lane fell back, which lane answered instead. Opened, the request on the wire, the input and
 * the output.
 */
import type { ReactNode } from "react";
import { LANE_BY_ID } from "@/lib/constants";
import type { LaneId, ToolCallView } from "@/lib/types";
import { formatDuration, toHost, toWireText } from "@/lib/utils";

type ToolChipProps = { call: ToolCallView };

const MARK_BY_STATUS = { running: "…", done: "✓", failed: "✗", stopped: "■" } as const;
const WORD_BY_STATUS = { running: "Running", done: "Done", failed: "Failed", stopped: "Stopped" } as const;

/**
 * What a cache hit means on a lane: on REST no request went out; on MCP the call did, and the server's cache answered.
 */
function toCacheNote(laneId: LaneId): string {
  return LANE_BY_ID[laneId].transport === "rest"
    ? "Answered from the cache: no request went out this time. This is the request that fetched it."
    : "Our MCP server answered from its cache: this request went out, and Open-Meteo wasn't asked again.";
}

/** Shows a JSON value, or a sentence as it is. */
function toDisplayText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** A tool call as a chip that opens; it's a <details> element, so it works with the keyboard and without script. */
export function ToolChip({ call }: ToolChipProps): ReactNode {
  const record = call.call;
  return (
    <details className={`tool-chip tool-chip-${call.status}`}>
      <summary>
        <span className="tool-chip-mark" aria-hidden="true">
          {MARK_BY_STATUS[call.status]}
        </span>
        <span className="visually-hidden">{WORD_BY_STATUS[call.status]}:</span>
        <code className="tool-chip-name">{call.tool}</code>
        <span className="tool-chip-input">{call.inputSummary}</span>
        {record ? (
          <span className="tool-chip-lane">
            {LANE_BY_ID[record.laneId].label} · {toHost(record.wire.url)} · {formatDuration(record.durationMs)}
            {record.cache === "hit" ? " · cached" : ""}
          </span>
        ) : null}
        {call.fallback ? (
          <span className="tool-chip-fallback">
            <span aria-hidden="true">! </span>
            {call.fallback.sentence}
          </span>
        ) : null}
      </summary>
      <div className="tool-chip-body">
        {call.resultSummary ? <p className="tool-chip-result">→ {call.resultSummary}</p> : null}
        {call.errorText ? <p className="tool-chip-error">{call.errorText}</p> : null}
        {record ? (
          <>
            <p className="tool-chip-label">On the wire</p>
            {record.cache === "hit" ? <p className="tool-chip-note">{toCacheNote(record.laneId)}</p> : null}
            <pre>{toWireText(record.wire)}</pre>
          </>
        ) : null}
        <p className="tool-chip-label">Input</p>
        <pre>{toDisplayText(call.input ?? "(still arriving)")}</pre>
        {call.output === undefined ? null : (
          <>
            <p className="tool-chip-label">Output</p>
            <pre>{toDisplayText(call.output)}</pre>
          </>
        )}
      </div>
    </details>
  );
}
