/*
 * tests/unit/sentry.test.ts: Sentry's settings: the DSN and the environment from the config; nothing private collected,
 * and no breadcrumbs; every request traced, its trace headers sent only to our own MCP server, and every query string
 * cut from a span before it's sent; and a request's trace marked with its id and ref.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { markTrace, toSentryOptions } from "@/lib/sentry";

// Sentry's spans, swapped for a root span that keeps the attributes it's given; none is active unless a test says so.
const { root } = vi.hoisted(() => ({ root: { isActive: false, attributes: {} as Record<string, unknown> } }));
vi.mock("@sentry/nextjs", () => ({
  getActiveSpan: () => (root.isActive ? { name: "child" } : undefined),
  getRootSpan: () => ({
    setAttributes: (attributes: Record<string, unknown>) => {
      Object.assign(root.attributes, attributes);
    },
  }),
}));

beforeEach(() => {
  root.isActive = false;
  root.attributes = {};
});

/** The settings Sentry's come from: a build's environment, and Sentry's DSN, if set. */
function configWith(environment: string, sentryDsn?: string) {
  return { build: { commit: "991a171", environment }, observability: { axiom: undefined, sentryDsn } };
}

describe("toSentryOptions", () => {
  it("sends the errors to the DSN, under the deployment's environment; without a DSN, nowhere", () => {
    const options = toSentryOptions(configWith("production", "https://k@o1.example/2"));
    expect(options.dsn).toBe("https://k@o1.example/2");
    expect(options.environment).toBe("production");
    expect(toSentryOptions(configWith("local")).dsn).toBeUndefined();
  });

  it("collects nothing private, and keeps no breadcrumbs", () => {
    const options = toSentryOptions(configWith("production"));
    expect(options.dataCollection).toEqual({
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      genAI: { inputs: false, outputs: false },
      stackFrameVariables: false,
    });
    expect(options.maxBreadcrumbs).toBe(0);
  });

  it("traces every request, and sends its trace headers to our own MCP server only", () => {
    const options = toSentryOptions(configWith("production"));
    expect(options.tracesSampleRate).toBe(1);
    const targets = options.tracePropagationTargets ?? [];
    const propagates = (url: string) =>
      targets.some((target) => (typeof target === "string" ? url.includes(target) : target.test(url)));
    expect(propagates("https://weather-chatbot-hazel.vercel.app/api/mcp")).toBe(true);
    for (const outside of [
      "https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast",
      "https://api.apify.com/v2/users/me",
      "https://geocoding-api.open-meteo.com/v1/search?name=Dallas&count=10",
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:streamGenerateContent?alt=sse",
      "https://us-east-1.aws.edge.axiom.co/v1/ingest/weather-chatbot?timestamp-field=ts",
    ]) {
      expect(propagates(outside)).toBe(false);
    }
  });

  it("cuts every query string from a span's name and texts, and drops the attributes that hold one alone", () => {
    const { beforeSendSpan, traceLifecycle } = toSentryOptions(configWith("production"));
    // The callback runs in the stream lifecycle only: pinned, so no setting can turn it off without a word.
    expect(traceLifecycle).toBe("stream");
    const span = {
      trace_id: "t1",
      span_id: "s1",
      name: "fetch GET https://geocoding-api.open-meteo.com/v1/search?name=Dallas&count=10",
      start_timestamp: 1,
      status: "ok" as const,
      is_segment: false,
      attributes: {
        "url.full": "https://geocoding-api.open-meteo.com/v1/search?name=Dallas&count=10",
        "url.query": "name=Dallas&count=10",
        "http.response.status_code": 200,
        "server.address": "geocoding-api.open-meteo.com",
      },
    };
    expect(beforeSendSpan?.(span)).toEqual({
      ...span,
      name: "fetch GET https://geocoding-api.open-meteo.com/v1/search",
      attributes: {
        "url.full": "https://geocoding-api.open-meteo.com/v1/search",
        "http.response.status_code": 200,
        "server.address": "geocoding-api.open-meteo.com",
      },
    });
  });
});

describe("markTrace", () => {
  it("marks the request's whole trace with its id and ref, so one id finds its lines, its trace and its errors", () => {
    root.isActive = true;
    markTrace("iad1::abc-1730-7f3a9c01");
    expect(root.attributes).toEqual({ requestId: "iad1::abc-1730-7f3a9c01", ref: "7f3a9c01" });
  });

  it("does nothing outside a trace", () => {
    expect(() => markTrace("iad1::abc-1730-7f3a9c01")).not.toThrow();
    expect(root.attributes).toEqual({});
  });
});
