/*
 * lib/utils.ts: every shared helper function: general-purpose, pure, and safe in the browser as well as on the server.
 */
import type { WireRequest } from "@/lib/types";

const MS_PER_SECOND = 1000;
const SHORTEST_SHOWN_MS = 50;
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;

/** Writes a request as it goes over the wire: the request line, the headers, then a blank line and the body. */
export function toWireText(request: WireRequest): string {
  const headerLines = Object.entries(request.headers).map(([name, value]) => `${name}: ${value}`);
  const head = [`${request.method} ${request.url}`, ...headerLines].join("\n");
  return request.body === undefined ? head : `${head}\n\n${request.body}`;
}

/** The host part of a URL, as written: "https://api.apify.com/v2/acts" → "api.apify.com". */
export function toHost(url: string): string {
  return url.replace(/^[a-z]+:\/\//i, "").split(/[/?#]/, 1)[0] ?? url;
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

/** An abort signal that fires after `ms`, or as soon as the parent signal does. */
export function timeoutSignal(ms: number, parentSignal?: AbortSignal): AbortSignal {
  const timeout = AbortSignal.timeout(ms);
  return parentSignal ? AbortSignal.any([timeout, parentSignal]) : timeout;
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
