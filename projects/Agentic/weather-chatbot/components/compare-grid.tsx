/*
 * components/compare-grid.tsx: the compare view: the same forecast call through all four lanes, side by side.
 */
import type { ReactNode } from "react";
import { LIVE_LANE_IDS } from "@/lib/constants";
import type { CompareCell, LaneId } from "@/lib/types";
import { toWireText } from "@/lib/utils";

type CompareGridProps = { cells: readonly CompareCell[] };

/** Four cells, one per lane: where the call goes, which credentials it carries, and the request itself. */
export function CompareGrid({ cells }: CompareGridProps): ReactNode {
  return (
    <section className="compare" aria-labelledby="compare-title">
      <h2 id="compare-title">The same forecast call, through each lane</h2>
      <p>
        The pair (no auth or with auth) decides where the call ends up and which tools the model sees; the door (REST or
        MCP) decides how the call travels. Within a pair, only the door changes.
      </p>
      <div className="compare-grid">
        {cells.map((cell) => (
          <article key={cell.lane.id} className="compare-cell">
            <h3>{cell.lane.label}</h3>
            <p className="compare-door">
              {cell.lane.door} · {cell.lane.auth === "none" ? "no credentials" : "a Bearer token"} ·{" "}
              <code>{cell.tool}</code>
            </p>
            <pre>{toWireText(cell.wire)}</pre>
            <p className="compare-note">
              {(LIVE_LANE_IDS as readonly LaneId[]).includes(cell.lane.id)
                ? "Live: ask in the chat on this lane, then open the forecast chip to see the request it really sent."
                : `Live from step ${cell.lane.builtInStep}; until then, this is the request it will send.`}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
