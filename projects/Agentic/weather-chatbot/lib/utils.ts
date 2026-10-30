/*
 * lib/utils.ts: every shared helper function: general-purpose, pure, and safe in the browser as well as on the server.
 */
import type { WireRequest } from "@/lib/types";

const MS_PER_SECOND = 1000;
const FAHRENHEIT_PER_CELSIUS = 1.8;
const FAHRENHEIT_AT_ZERO_CELSIUS = 32;
const TENTHS = 10;
const SHORTEST_SHOWN_MS = 50;
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;
const DATE_CHARS = 10;
// How far down an error's causes to look for an HTTP status: a client wraps the response's error once or twice.
const MAX_CAUSE_DEPTH = 5;
const REQUEST_ID_CHARS = 16;
// A request id we take from a header: letters, digits and : . _ -, as in Vercel's "iad1::abcde-1730211234567-f3c2b1".
const REQUEST_ID_PATTERN = /^[\w:.-]{1,128}$/;
const REF_CHARS = 8;

/** Writes a request as it goes over the wire: the request line, the headers, then a blank line and the body. */
export function toWireText(request: WireRequest): string {
  const headerLines = Object.entries(request.headers).map(([name, value]) => `${name}: ${value}`);
  const head = [`${request.method} ${request.url}`, ...headerLines].join("\n");
  return request.body === undefined ? head : `${head}\n\n${request.body}`;
}

/**
 * A request as a client sends it, with each header named in `masks` shown as its stand-in, never its value: what a
 * chip's wire view shows. Header names come out lowercase, as fetch's Headers gives them.
 */
export function toWireRequest(
  input: string | URL | Request,
  init: RequestInit | undefined,
  masks: Readonly<Record<string, string>>,
): WireRequest {
  const headers = Object.fromEntries(
    [...new Headers(init?.headers).entries()].map(([name, value]) => [name, masks[name] ?? value]),
  );
  const body = typeof init?.body === "string" ? init.body : undefined;
  return { method: init?.method === "GET" ? "GET" : "POST", url: String(input), headers, body };
}

/** The MCP tools/call request that carried a call: the last one sent with this tool's name and these arguments. */
export function findToolsCall(sent: readonly WireRequest[], name: string, input: unknown): WireRequest | undefined {
  const wanted = JSON.stringify(input);
  return sent.findLast((request) => {
    const message: unknown = request.body === undefined ? undefined : JSON.parse(request.body);
    if (typeof message !== "object" || message === null || !("method" in message) || !("params" in message)) {
      return false;
    }
    const params = message.params as { name?: unknown; arguments?: unknown };
    return message.method === "tools/call" && params.name === name && JSON.stringify(params.arguments) === wanted;
  });
}

/** An MCP tool result's text parts, joined; a result without a content list has no text. */
export function toResultText(result: object): string {
  const content: unknown = "content" in result ? result.content : undefined;
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .map((part: unknown) =>
      typeof part === "object" && part !== null && "text" in part && typeof part.text === "string" ? part.text : "",
    )
    .join("");
}

/** The HTTP status an error carries, on itself or on one of its causes; none when no response came back. */
export function toStatusCode(error: unknown): number | undefined {
  let current: unknown = error;
  for (let depth = 0; depth < MAX_CAUSE_DEPTH && typeof current === "object" && current !== null; depth += 1) {
    if ("statusCode" in current && typeof current.statusCode === "number") {
      return current.statusCode;
    }
    current = "cause" in current ? current.cause : undefined;
  }
  return undefined;
}

/**
 * The fields a check found wrong, by name only, never a value, and without the index of the item or value that broke
 * it: "daily.time", not "daily.time.3"; a check of the whole gives its own words.
 */
export function toFieldNames(issues: readonly { path: readonly PropertyKey[]; message: string }[]): string {
  const fields = issues.map((issue) => issue.path.filter((key) => typeof key !== "number").join(".") || issue.message);
  return [...new Set(fields)].join(", ");
}

/** The host part of a URL, as written: "https://api.apify.com/v2/acts" → "api.apify.com". */
export function toHost(url: string): string {
  return url.replace(/^[a-z]+:\/\//i, "").split(/[/?#]/, 1)[0] ?? url;
}

/** A temperature in °F, from °C, to a tenth of a degree, as Open-Meteo gives it: 11.9 → 53.4. */
export function celsiusToFahrenheit(celsius: number): number {
  return Math.round((celsius * FAHRENHEIT_PER_CELSIUS + FAHRENHEIT_AT_ZERO_CELSIUS) * TENTHS) / TENTHS;
}

/** Rounds a latitude or longitude; 2 decimals is about 1 km. */
export function roundCoordinate(value: number, decimals = 2): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/** A time in seconds, with one decimal: 587 → "0.6 s"; anything under 50 ms is "<0.1 s". */
export function formatDuration(ms: number): string {
  return ms < SHORTEST_SHOWN_MS ? "<0.1 s" : `${(ms / MS_PER_SECOND).toFixed(1)} s`;
}

/** A moment's clock time in a time zone, 24-hour: ("2026-10-29T19:07:00Z", "Europe/Paris") → "20:07". */
export function formatLocalTime(isoTime: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(
    new Date(isoTime),
  );
}

/** The weekday of a calendar date, written "2026-10-30": "Friday". The date is read as written, in no time zone. */
export function toWeekday(isoDate: string): string {
  const day = new Date(`${isoDate}T00:00:00Z`).getUTCDay();
  return WEEKDAYS[day] ?? "";
}

/**
 * A moment's date and time in a time zone, to the minute, written as Open-Meteo writes local times:
 * ("2026-10-30T03:00:00Z", "America/Chicago") → "2026-10-29T22:00".
 */
export function toLocalDateTime(isoTime: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(isoTime));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((each) => each.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

/** A calendar date some days later, written "2026-10-31": ("2026-10-31", 1) → "2026-11-01". Read in no time zone. */
export function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, DATE_CHARS);
}

/** A new request id, for a request that didn't bring one: 16 random hex characters. */
export function newRequestId(): string {
  return crypto.randomUUID().replaceAll("-", "").slice(0, REQUEST_ID_CHARS);
}

/** The id to log a request with: the first of these header values that looks like a request id, else a new one. */
export function toRequestId(...headerValues: (string | null)[]): string {
  return (
    headerValues.find((value): value is string => value !== null && REQUEST_ID_PATTERN.test(value)) ?? newRequestId()
  );
}

/** A request id as a short ref for people, its last 8 letters and digits: "iad1::abc-1730-7f3a9c01" → "7f3a9c01". */
export function toRef(requestId: string): string {
  return requestId.replace(/[^a-z0-9]/gi, "").slice(-REF_CHARS);
}

/** Wraps a function so it runs only the first time it's called; later calls get the first call's result. */
export function once<T>(fn: () => T): () => T {
  let hasRun = false;
  let result: T;
  return () => {
    if (!hasRun) {
      hasRun = true;
      result = fn();
    }
    return result;
  };
}

/**
 * Why a signal fired: "timeout" when a time limit fired it (a TimeoutError), "stop" for any other reason (Stop, a
 * closed browser, which Next.js marks with its own error, or the answer's end), "none" when it hasn't fired.
 */
export function toAbortKind(signal: AbortSignal | undefined): "none" | "timeout" | "stop" {
  if (signal?.aborted !== true) {
    return "none";
  }
  const reason: unknown = signal.reason;
  return reason instanceof Error && reason.name === "TimeoutError" ? "timeout" : "stop";
}

/** An abort signal that fires after `ms`, or as soon as the parent signal does. */
export function timeoutSignal(ms: number, parentSignal?: AbortSignal): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return parentSignal ? AbortSignal.any([timeout, parentSignal]) : timeout;
}

/**
 * Waits for a promise, but at most `ms`: past that, it's left to settle on its own, and whether it fails isn't asked.
 * For clean-up that mustn't hold up what comes after it.
 */
export async function waitAtMost(promise: Promise<unknown>, ms: number): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeUp = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, ms);
  });
  try {
    await Promise.race([
      promise.then(
        () => undefined,
        () => undefined,
      ),
      timeUp,
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/** A Retry-After header's wait, in milliseconds; undefined when it's missing or isn't a number of seconds. */
export function toRetryAfterMs(header: string | null): number | undefined {
  if (header === null || !/^\d+$/.test(header.trim())) {
    return undefined;
  }
  return Number(header.trim()) * MS_PER_SECOND;
}

type RetryOptions = {
  tries: number;
  shouldRetry: (error: unknown) => boolean;
  waitMs: (error: unknown) => number;
  signal?: AbortSignal;
};

/**
 * Runs a task, and runs it again after a wait while it fails, `shouldRetry` says so, and tries are left. Once the
 * signal fires, it stops with the signal's reason.
 */
export async function withRetry<T>(task: () => Promise<T>, options: RetryOptions): Promise<T> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await task();
    } catch (error) {
      options.signal?.throwIfAborted();
      if (attempt >= options.tries || !options.shouldRetry(error)) {
        throw error;
      }
      await wait(options.waitMs(error), options.signal);
    }
  }
}

/** Waits `ms`; stops early, with the signal's reason, if the signal fires. */
function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort(): void {
      clearTimeout(timer);
      reject(signal?.reason);
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
