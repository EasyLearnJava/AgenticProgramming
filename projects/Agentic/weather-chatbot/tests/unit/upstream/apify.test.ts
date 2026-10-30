/*
 * tests/unit/upstream/apify.test.ts: the Apify client: the run's request (the token in the header, masked in the
 * record, never in the URL; the build, time and cost in the URL), its items, every failure as one of our classes, and
 * its log lines. The 401 is Apify's real answer to a fake token; the other error bodies are written in the shape
 * Apify's API documents.
 */
import { describe, expect, it } from "vitest";
import {
  AuthError,
  BudgetExceededError,
  ContractError,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import { type ActorRunInput, createApifyClient } from "@/lib/upstream/apify";
import { type ApifyAnswer, apifyError, createApifyFetch } from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

const TOKEN = "test-token-not-real";
const NOW = new Date("2026-10-29T16:00:00Z");
const PARIS: ActorRunInput = {
  locations: [{ name: "Paris", latitude: 48.85, longitude: 2.35 }],
  forecastDays: 2,
  mode: "hourly",
};

/** A client whose fetch gives these answers; and the requests it sent, and the lines it logged. */
function clientWith(answers: ApifyAnswer[] | typeof fetch) {
  const fake = typeof answers === "function" ? { fetch: answers, requests: [] } : createApifyFetch(answers);
  const client = createApifyClient({ token: TOKEN, fetch: fake.fetch, now: () => NOW });
  const { log, lines } = createTestLog();
  return { client, log, lines, requests: fake.requests };
}

describe("the run's request", () => {
  it("is one POST: the token in its Authorization header, the limits in the URL, the input as its body", async () => {
    const { client, log, requests } = clientWith([{ fixture: "actor-paris-assumed", status: 201 }]);
    const run = await client.runActor(PARIS, { log });
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      method: "POST",
      url:
        "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items" +
        "?build=1.0.9&timeout=18&maxTotalChargeUsd=0.01",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify(PARIS),
    });
    expect(run.items).toHaveLength(1);
    expect(run.fetchedAt).toBe(NOW.toISOString());
  });

  it("records the request with the token masked: what the wire view shows; the token is never in the URL", async () => {
    const { client, log } = clientWith([{ fixture: "actor-paris-assumed", status: 201 }]);
    const run = await client.runActor(PARIS, { log });
    expect(run.request.headers).toEqual({ authorization: "Bearer <APIFY_TOKEN>", "content-type": "application/json" });
    expect(JSON.stringify(run.request)).not.toContain(TOKEN);
    expect(run.request.url).not.toContain("token");
  });

  it("writes one upstream.http line: the host, the status, the time, one try; never the token", async () => {
    const { client, log, lines } = clientWith([{ fixture: "actor-paris-assumed", status: 201 }]);
    await client.runActor(PARIS, { log });
    expect(lines).toEqual([
      expect.objectContaining({
        level: "info",
        event: "upstream.http",
        upstream: "apify",
        host: "api.apify.com",
        status: "ok",
        httpStatus: 201,
        attempts: 1,
        items: 1,
      }),
    ]);
    expect(JSON.stringify(lines)).not.toContain(TOKEN);
  });
});

describe("a failed run", () => {
  it("a token Apify doesn't accept: AuthError, with Apify's own words, as its real 401 answer gives them", async () => {
    const { client, log, lines } = clientWith([{ fixture: "error-401-fake-token", status: 401 }]);
    const error = await client.runActor(PARIS, { log }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(AuthError);
    expect((error as Error).message).toBe(
      "Apify answered 401: user-or-token-not-found (User was not found or authentication token is not valid).",
    );
    expect(lines).toEqual([expect.objectContaining({ status: "failed", httpStatus: 401, errorClass: "AuthError" })]);
  });

  it("each status as our class: 403 auth, 402 budget, 408 timeout, 429 busy, 5xx unavailable", async () => {
    const cases = [
      [apifyError(403, "insufficient-permissions", "The token can't run Actors."), AuthError],
      [apifyError(402, "x402-payment-required", "Payment required."), BudgetExceededError],
      [apifyError(408, "run-timeout-exceeded", "The run took too long."), UpstreamTimeoutError],
      [apifyError(429, "rate-limit-exceeded", "Too many requests."), UpstreamRateLimitedError],
      [apifyError(503, "server-error", "Try again later."), UpstreamUnavailableError],
    ] as const;
    for (const [answer, errorClass] of cases) {
      const { client, log } = clientWith([answer]);
      await expect(client.runActor(PARIS, { log })).rejects.toBeInstanceOf(errorClass);
    }
  });

  it("refused input: ContractError, with Apify's error type only, since its message can quote the input", async () => {
    const { client, log } = clientWith([apifyError(400, "invalid-input", "Input is not valid: Paris, 48.85")]);
    const error = await client.runActor(PARIS, { log }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as Error).message).toBe("Apify refused the run with 400: invalid-input.");
  });

  it("an answer that isn't a list of items, or isn't JSON: ContractError", async () => {
    for (const body of ['{"items": []}', "not json"]) {
      const { client, log } = clientWith([() => new Response(body, { status: 201 })]);
      await expect(client.runActor(PARIS, { log })).rejects.toBeInstanceOf(ContractError);
    }
  });

  it("no answer: unavailable, keeping the cause; past the tool's budget: a timeout", async () => {
    const refusing = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const unreachable = clientWith(refusing);
    const error = await unreachable.client.runActor(PARIS, { log: unreachable.log }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(UpstreamUnavailableError);
    expect((error as Error).cause).toBeInstanceOf(TypeError);
    const slow = clientWith(hangingFetch);
    await expect(
      slow.client.runActor(PARIS, { log: slow.log, signal: AbortSignal.timeout(20) }),
    ).rejects.toBeInstanceOf(UpstreamTimeoutError);
  });

  it("a stop while the answer is still arriving is a stop, not an answer we can't read", async () => {
    const controller = new AbortController();
    // The body never ends, until the stop errors it, as a real fetch's body does.
    const arriving = () =>
      new Response(
        new ReadableStream({
          start(body) {
            controller.signal.addEventListener("abort", () => body.error(controller.signal.reason), { once: true });
          },
        }),
        { status: 201 },
      );
    const { client, log, lines } = clientWith([arriving]);
    const pending = client.runActor(PARIS, { log, signal: controller.signal });
    controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" }));
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(lines).toEqual([]);
  });

  it("a stop is passed on as it is, and not logged", async () => {
    const { client, log, lines } = clientWith(hangingFetch);
    const controller = new AbortController();
    const pending = client.runActor(PARIS, { log, signal: controller.signal });
    controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" }));
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(lines).toEqual([]);
  });
});
