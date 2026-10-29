/*
 * lib/logger.ts: the app's one way to log (PLAN.md 9.1): pino, one JSON object per line, written to stdout, which
 * Vercel's logs pick up. Every line names the build it came from; a request's lines carry its request id, and a lane's
 * its lane, door and auth. Secrets are redacted, and a question is logged as its length, never its text.
 */
import "server-only";
import { type DestinationStream, type Logger, pino } from "pino";
import { config, type LogLevel } from "@/lib/config";
import { LANE_BY_ID, MAX_LOGGED_CAUSE_CHARS, MAX_LOGGED_STACK_LINES } from "@/lib/constants";
import { type AppError, UnexpectedError } from "@/lib/errors";
import type { LaneId } from "@/lib/types";

export type { Logger };

// Anything that could hold a secret, in case a line ever carries it: a header, a token, a key. None does today.
const REDACTED_PATHS = [
  "authorization",
  "headers.authorization",
  'headers["x-vercel-protection-bypass"]',
  "*.authorization",
  '*.headers["x-vercel-protection-bypass"]',
  "token",
  "*.token",
  "apiKey",
  "*.apiKey",
  "bypassSecret",
];

type LoggerOptions = { level?: LogLevel; destination?: DestinationStream };

/**
 * A logger: the build's own fields on every line (its environment, commit and deployment), the level as a word, the
 * time as `ts`. It writes to stdout synchronously, so a function that ends right after a line still sends it.
 */
export function createLogger({
  level = config.log.level,
  destination = pino.destination({ dest: 1, sync: true }),
}: LoggerOptions = {}): Logger {
  return pino(
    {
      level,
      base: { env: config.build.environment, commit: config.build.commit, deploymentId: config.deployment.id },
      timestamp: () => `,"ts":"${new Date().toISOString()}"`,
      formatters: { level: (label) => ({ level: label }) },
      redact: { paths: REDACTED_PATHS, censor: "[redacted]" },
    },
    destination,
  );
}

/** The app's logger. Each request logs through a child of it, with the request's id. */
export const logger: Logger = createLogger();

/** The fields on every line about a lane: which lane, which door (REST or MCP), and which auth. */
export function toLaneFields(laneId: LaneId): { lane: LaneId; transport: string; auth: string } {
  const { transport, auth } = LANE_BY_ID[laneId];
  return { lane: laneId, transport, auth };
}

/** A failure's cause, for its line: the cause's class and message (cut short); for a bug, where it happened too. */
function toCauseFields(error: AppError): Record<string, string> {
  const { cause } = error;
  if (cause === undefined) {
    return {};
  }
  const { name, message, stack } = cause instanceof Error ? cause : { name: typeof cause, message: String(cause) };
  const fields: Record<string, string> = { causeClass: name, cause: message.slice(0, MAX_LOGGED_CAUSE_CHARS) };
  if (error instanceof UnexpectedError && stack !== undefined) {
    fields.stack = stack.split("\n").slice(0, MAX_LOGGED_STACK_LINES).join("\n");
  }
  return fields;
}

/**
 * Logs a failure, at its class's level: the event and its fields, "failed", the class, our message, whether trying
 * again can help, and its cause.
 */
export function logFailure(
  log: Logger,
  event: string,
  error: AppError,
  fields: Readonly<Record<string, unknown>> = {},
): void {
  log[error.level]({
    event,
    ...fields,
    status: "failed",
    errorClass: error.name,
    message: error.message,
    isRetryable: error.isRetryable,
    ...toCauseFields(error),
  });
}
