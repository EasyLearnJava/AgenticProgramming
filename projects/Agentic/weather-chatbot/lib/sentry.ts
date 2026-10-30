/*
 * lib/sentry.ts: Sentry's settings (step 9): the server's errors, with their stack traces, and nothing private. No IP
 * addresses, cookies, headers, bodies, query strings, AI prompts or answers, or a stack frame's variables: the
 * question, which we never log, goes only to the model. No breadcrumbs either: our own lines, in Axiom, tell what led
 * up to an error, found by its request id. And none of Sentry's trace headers on our calls to Gemini, Open-Meteo or
 * Apify. The release is the commit, which Sentry reads from Vercel itself.
 */
import type { NodeOptions } from "@sentry/nextjs";
import type { Config } from "@/lib/config";

/** Sentry's settings for the server; without a DSN, on a laptop or in CI, Sentry stays off. */
export function toSentryOptions({ build, observability }: Pick<Config, "build" | "observability">): NodeOptions {
  return {
    dsn: observability.sentryDsn,
    environment: build.environment,
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      genAI: { inputs: false, outputs: false },
      stackFrameVariables: false,
    },
    maxBreadcrumbs: 0,
    tracePropagationTargets: [],
  };
}
