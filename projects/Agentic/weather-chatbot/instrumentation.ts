/*
 * instrumentation.ts: runs once when the server starts (step 9). It starts Sentry, with the settings in lib/sentry.ts:
 * Sentry gets each failure logged as an error (lib/logger.ts), and any error Next.js catches in a request, with its
 * stack trace. Errors only, for now: no traces. Without SENTRY_DSN, on a laptop or in CI, Sentry stays off.
 */
import * as Sentry from "@sentry/nextjs";
import { toSentryOptions } from "@/lib/sentry";

/** Starts Sentry on the server; Next.js calls it once, when the server starts. */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { config } = await import("@/lib/config");
    Sentry.init(toSentryOptions(config));
  }
}

export const onRequestError = Sentry.captureRequestError;
