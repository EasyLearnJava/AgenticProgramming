/*
 * lib/logger.ts: the app's one way to log (PLAN.md 9.1): pino, one JSON object per line, written to stdout, which
 * Vercel's logs pick up, and kept for Axiom when it's set up (step 9). Every line names the build it came from; a
 * request's lines carry its request id, and a lane's its lane, door and auth. Secrets are redacted, and a question is
 * logged as its length, never its text. A failure logged as an error also goes to Sentry, with its stack trace; a
 * request's end calls flushLogs(), which sends Axiom its lines and Sentry its errors.
 */
import "server-only";
import * as Sentry from "@sentry/nextjs";
import { type DestinationStream, type Logger, pino } from "pino";
import { config, type LogLevel } from "@/lib/config";
import { LANE_BY_ID, MAX_LOGGED_CAUSE_CHARS, MAX_LOGGED_STACK_LINES, SENTRY_FLUSH_TIMEOUT_MS } from "@/lib/constants";
import { type AppError, UnexpectedError } from "@/lib/errors";
import { createLogShipper } from "@/lib/log-shipper";
import type { LaneId } from "@/lib/types";
import { toRef } from "@/lib/utils";

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

// Axiom gets each line too, when its token and dataset are set (step 9).
const axiom = config.observability.axiom;
const shipper = axiom === undefined ? undefined : createLogShipper(axiom);

/**
 * Where the app's lines go: stdout, synchronously, so a function that ends right after a line still sends it; and
 * Axiom's batch, when it's set up.
 */
function toAppDestination(level: LogLevel): DestinationStream {
  const stdout = pino.destination({ dest: 1, sync: true });
  return shipper === undefined
    ? stdout
    : pino.multistream([
        { level, stream: stdout },
        { level, stream: shipper },
      ]);
}

/**
 * A logger: the build's own fields on every line (its environment, commit and deployment), the level as a word, the
 * time as `ts`.
 */
export function createLogger({
  level = config.log.level,
  destination = toAppDestination(level),
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

/**
 * Sends what waits to go out, each within 2 s: Axiom the lines kept since its last batch, and Sentry the errors it
 * holds; nothing for one that isn't set up. Never fails.
 */
export async function flushLogs(): Promise<void> {
  await Promise.all([shipper?.flush(), Sentry.flush(SENTRY_FLUSH_TIMEOUT_MS)]);
}

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

// The fields of a request's lines that go to Sentry as tags: they find its lines in Axiom, and say where it failed.
const SENTRY_TAG_FIELDS = ["requestId", "route", "lane", "tool"] as const;

/** A failure's Sentry tags: its event, its request's own fields, and its ref, as the page's sentence gives it. */
function toSentryTags(log: Logger, event: string): Record<string, string> {
  const bindings = log.bindings();
  const tags: Record<string, string> = { event };
  for (const name of SENTRY_TAG_FIELDS) {
    const value = bindings[name];
    if (typeof value === "string") {
      tags[name] = value;
    }
  }
  if (tags.requestId !== undefined) {
    tags.ref = toRef(tags.requestId);
  }
  return tags;
}

/**
 * Logs a failure, at its class's level: the event and its fields, "failed", the class, our message, whether trying
 * again can help, and its cause. One logged as an error (a bug, the model failing, a broken contract or setting) also
 * goes to Sentry, tagged with its request's id and ref.
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
  if (error.level === "error") {
    Sentry.captureException(error, { tags: toSentryTags(log, event), extra: { ...fields } });
  }
}
