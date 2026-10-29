/*
 * lib/logger.ts: the app's one way to log: one JSON line per event, which Vercel's logs pick up. For now it logs
 * failures only, with the error's class and our own message, never a question's text or an upstream's whole answer.
 * Step 5 puts pino inside, with request ids, the lane fields and redaction (PLAN.md 9.1).
 */
import "server-only";

/** Logs a failure: the event, the error's class and message, and a few plain fields (the tool, the lane). */
export function logError(event: string, error: unknown, fields: Readonly<Record<string, string>> = {}): void {
  const { name, message } = error instanceof Error ? error : { name: "NonError", message: String(error) };
  console.error(JSON.stringify({ level: "error", event, ...fields, errorClass: name, message }));
}
