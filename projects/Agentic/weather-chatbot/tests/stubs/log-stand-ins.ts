/*
 * tests/stubs/log-stand-ins.ts: a logger that keeps its lines, read back as objects, for a test to check; the app's
 * own logger is silent in the tests.
 */
import { createLogger, type Logger } from "@/lib/logger";

/** A line as the logger wrote it, read back from its JSON. */
export type LogLine = Record<string, unknown>;

/** A logger at "info" whose lines land in `lines`, as objects; `events` lists each line's event and level. */
export function createTestLog(): { log: Logger; lines: LogLine[]; events: () => string[] } {
  const lines: LogLine[] = [];
  const log = createLogger({
    level: "info",
    destination: {
      write: (line: string) => {
        lines.push(JSON.parse(line) as LogLine);
      },
    },
  });
  return { log, lines, events: () => lines.map((line) => `${String(line.level)} ${String(line.event)}`) };
}
