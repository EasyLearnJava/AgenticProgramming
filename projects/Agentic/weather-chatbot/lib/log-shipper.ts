/*
 * lib/log-shipper.ts: sends the app's log lines to Axiom (step 9). Vercel's Hobby plan keeps logs for an hour and can't
 * forward them, so the app does it itself: each line is kept as it's written, and a request's end sends what's kept,
 * in one batch, within 2 s. Sending never fails a request: a batch Axiom doesn't take is reported on stderr, and
 * dropped.
 */
import "server-only";
import { AXIOM_FLUSH_TIMEOUT_MS, AXIOM_INGEST_HOST, AXIOM_MAX_PENDING_LINES } from "@/lib/constants";

/** A destination for pino's lines that keeps each one for Axiom, and sends those it keeps when asked. */
export type LogShipper = { write: (line: string) => void; flush: () => Promise<void> };

type LogShipperOptions = {
  dataset: string;
  token: string;
  fetch?: typeof fetch;
  maxPendingLines?: number;
  timeoutMs?: number;
  report?: (line: string) => void;
};

/** Axiom's ingest address for a dataset; the time of each event is its line's `ts`. */
export function toAxiomIngestUrl(dataset: string): string {
  return `https://${AXIOM_INGEST_HOST}/v1/ingest/${encodeURIComponent(dataset)}?timestamp-field=ts`;
}

/**
 * Keeps each line it's given; flush() sends them to Axiom as NDJSON, with the token, in one request. Past
 * `maxPendingLines`, lines are dropped and counted, so a flush that never comes can't fill the memory.
 */
export function createLogShipper({
  dataset,
  token,
  fetch: send = fetch,
  maxPendingLines = AXIOM_MAX_PENDING_LINES,
  timeoutMs = AXIOM_FLUSH_TIMEOUT_MS,
  report = (line) => process.stderr.write(`${line}\n`),
}: LogShipperOptions): LogShipper {
  let pending: string[] = [];
  let dropped = 0;
  return {
    write(line) {
      if (pending.length >= maxPendingLines) {
        dropped += 1;
        return;
      }
      pending.push(line);
    },
    async flush() {
      const lines = pending;
      const lost = dropped;
      pending = [];
      dropped = 0;
      if (lost > 0) {
        report(JSON.stringify({ level: "warn", event: "axiom.dropped", lines: lost }));
      }
      if (lines.length === 0) {
        return;
      }
      // A line Axiom can't take is said on stderr, which Vercel's own logs keep: never through the logger, whose lines
      // come back here.
      try {
        const response = await send(toAxiomIngestUrl(dataset), {
          method: "POST",
          headers: { authorization: `Bearer ${token}`, "content-type": "application/x-ndjson" },
          body: lines.join(""),
          signal: AbortSignal.timeout(timeoutMs),
        });
        if (!response.ok) {
          report(
            JSON.stringify({ level: "warn", event: "axiom.failed", httpStatus: response.status, lines: lines.length }),
          );
        }
        // Nothing past the reply's status is needed, and a reply left unread holds its connection until it's collected.
        // Letting it go can't fail the batch, whose status has already said how it went.
        await response.body?.cancel().catch(() => undefined);
      } catch (error) {
        const reason = error instanceof Error ? error.name : "unknown";
        report(JSON.stringify({ level: "warn", event: "axiom.failed", reason, lines: lines.length }));
      }
    },
  };
}
