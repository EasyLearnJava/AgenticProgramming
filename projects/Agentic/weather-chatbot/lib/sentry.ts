/*
 * lib/sentry.ts: Sentry's settings (step 9): the server's errors, with their stack traces, and its traces, with nothing
 * private. No IP addresses, cookies, headers, bodies, query strings, AI prompts or answers, or a stack frame's
 * variables: the question, which we never log, goes only to the model. No breadcrumbs either: our own lines, in Axiom,
 * tell what led up to an error, found by its request id. Every request is traced; its trace headers go to our own MCP
 * server only, so one trace runs through both functions, and never to Gemini, Open-Meteo or Apify; and every query
 * string is cut from a span before it's sent, since an address's query can hold a place. The release is the commit,
 * which Sentry reads from Vercel itself.
 */
import { getActiveSpan, getRootSpan, type NodeOptions } from "@sentry/nextjs";
import type { Config } from "@/lib/config";
import { MCP_API_PATH, SENTRY_TRACES_SAMPLE_RATE } from "@/lib/constants";
import { toRef, withoutQueryStrings } from "@/lib/utils";

/** A span as Sentry is about to send it. */
type OutgoingSpan = Parameters<NonNullable<NodeOptions["beforeSendSpan"]>>[0];

// The attributes that hold a query string alone, without its "?".
const QUERY_ATTRIBUTES = new Set(["url.query", "http.query"]);
// Our own MCP server's address, on whichever deployment: the one place a trace's headers go.
const OUR_MCP_SERVER = new RegExp(`${MCP_API_PATH}$`);

/** A span without query strings: its name and every text attribute cut, and the attributes that hold one alone gone. */
function toSpanWithoutQueries(span: OutgoingSpan): OutgoingSpan {
  const attributes = Object.fromEntries(
    Object.entries(span.attributes)
      .filter(([name]) => !QUERY_ATTRIBUTES.has(name))
      .map(([name, value]) => [name, typeof value === "string" ? withoutQueryStrings(value) : value]),
  );
  return { ...span, name: withoutQueryStrings(span.name), attributes: attributes as OutgoingSpan["attributes"] };
}

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
    tracesSampleRate: SENTRY_TRACES_SAMPLE_RATE,
    tracePropagationTargets: [OUR_MCP_SERVER],
    // The span callback runs in the stream lifecycle only: pinned, so a setting can't turn the cut off without a word.
    traceLifecycle: "stream",
    beforeSendSpan: toSpanWithoutQueries,
  };
}

/** Marks a request's whole trace with its id and ref, so one id finds its lines in Axiom, its trace and its errors. */
export function markTrace(requestId: string): void {
  const span = getActiveSpan();
  if (span !== undefined) {
    getRootSpan(span).setAttributes({ requestId, ref: toRef(requestId) });
  }
}
