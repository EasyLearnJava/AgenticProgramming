/*
 * tests/unit/sentry.test.ts: Sentry's settings: the DSN and the environment from the config; nothing private collected,
 * no breadcrumbs, and no trace headers on our calls out.
 */
import { describe, expect, it } from "vitest";
import { toSentryOptions } from "@/lib/sentry";

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

  it("collects nothing private, keeps no breadcrumbs, and adds no trace headers to our calls out", () => {
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
    expect(options.tracePropagationTargets).toEqual([]);
  });
});
