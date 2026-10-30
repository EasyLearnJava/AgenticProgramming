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
import { type ActorRunInput, checkApifyToken, createApifyClient } from "@/lib/upstream/apify";
import { type ApifyAnswer, apifyError, createApifyFetch } from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

const TOKEN = "test-token-not-real";
const NOW = new Date("2026-10-29T16:00:00Z");
// The input of the live check's daily run.
const DALLAS: ActorRunInput = {
  locations: [{ name: "Dallas", latitude: 32.78, longitude: -96.81 }],
  forecastDays: 3,
  mode: "daily",
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
    const { client, log, requests } = clientWith([{ fixture: "actor-dallas-daily", status: 201 }]);
    const run = await client.runActor(DALLAS, { log });
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      method: "POST",
      url:
        "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items" +
        "?build=1.0.9&timeout=18&maxTotalChargeUsd=0.01",
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify(DALLAS),
    });
    expect(run.items).toHaveLength(3);
    expect(run.fetchedAt).toBe(NOW.toISOString());
  });

  it("records the request with the token masked: what the wire view shows; the token is never in the URL", async () => {
    const { client, log } = clientWith([{ fixture: "actor-dallas-daily", status: 201 }]);
    const run = await client.runActor(DALLAS, { log });
    expect(run.request.headers).toEqual({ authorization: "Bearer <APIFY_TOKEN>", "content-type": "application/json" });
    expect(JSON.stringify(run.request)).not.toContain(TOKEN);
    expect(run.request.url).not.toContain("token");
  });

  it("writes one upstream.http line: the host, the status, the time, one try; never the token", async () => {
    const { client, log, lines } = clientWith([{ fixture: "actor-dallas-daily", status: 201 }]);
    await client.runActor(DALLAS, { log });
    expect(lines).toEqual([
      expect.objectContaining({
        level: "info",
        event: "upstream.http",
        upstream: "apify",
        host: "api.apify.com",
        status: "ok",
        httpStatus: 201,
        attempts: 1,
        items: 3,
      }),
    ]);
    expect(JSON.stringify(lines)).not.toContain(TOKEN);
  });
});

describe("a failed run", () => {
  it("a token Apify doesn't accept: AuthError, with Apify's own words, as its real 401 answer gives them", async () => {
    const { client, log, lines } = clientWith([{ fixture: "error-401-fake-token", status: 401 }]);
    const error = await client.runActor(DALLAS, { log }).catch((caught: unknown) => caught);
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
      await expect(client.runActor(DALLAS, { log })).rejects.toBeInstanceOf(errorClass);
    }
  });

  it("refused input: ContractError, with Apify's error type only, since its message can quote the input", async () => {
    const { client, log } = clientWith([apifyError(400, "invalid-input", "Input is not valid: Dallas, 32.78")]);
    const error = await client.runActor(DALLAS, { log }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as Error).message).toBe("Apify refused the run with 400: invalid-input.");
  });

  it("an answer that isn't a list of items, or isn't JSON: ContractError", async () => {
    for (const body of ['{"items": []}', "not json"]) {
      const { client, log } = clientWith([() => new Response(body, { status: 201 })]);
      await expect(client.runActor(DALLAS, { log })).rejects.toBeInstanceOf(ContractError);
    }
  });

  it("no answer: unavailable, keeping the cause; past the tool's budget: a timeout", async () => {
    const refusing = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const unreachable = clientWith(refusing);
    const error = await unreachable.client
      .runActor(DALLAS, { log: unreachable.log })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(UpstreamUnavailableError);
    expect((error as Error).cause).toBeInstanceOf(TypeError);
    const slow = clientWith(hangingFetch);
    await expect(
      slow.client.runActor(DALLAS, { log: slow.log, signal: AbortSignal.timeout(20) }),
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
    const pending = client.runActor(DALLAS, { log, signal: controller.signal });
    controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" }));
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(lines).toEqual([]);
  });

  it("a stop is passed on as it is, and not logged", async () => {
    const { client, log, lines } = clientWith(hangingFetch);
    const controller = new AbortController();
    const pending = client.runActor(DALLAS, { log, signal: controller.signal });
    controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" }));
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(lines).toEqual([]);
  });
});

describe("checking the token, running nothing", () => {
  it("is one GET of the account behind it, the token in its header only; the account's details go unread", async () => {
    const reply = new Response(JSON.stringify({ data: { username: "someone" } }), { status: 200 });
    const { fetch, requests } = createApifyFetch([() => reply]);
    const { log, lines } = createTestLog();
    await expect(checkApifyToken({ token: TOKEN, fetch, now: () => NOW, log })).resolves.toBeUndefined();
    expect(requests).toEqual([
      {
        url: "https://api.apify.com/v2/users/me",
        method: "GET",
        headers: { authorization: `Bearer ${TOKEN}` },
        body: "",
      },
    ]);
    expect(reply.bodyUsed).toBe(true);
    expect(lines).toEqual([
      expect.objectContaining({ event: "upstream.http", host: "api.apify.com", status: "ok", httpStatus: 200 }),
    ]);
    expect(JSON.stringify(lines)).not.toContain("someone");
    expect(JSON.stringify(lines)).not.toContain(TOKEN);
  });

  it("a token Apify doesn't take: AuthError, from Apify's real 401, the same at users/me as at a run", async () => {
    const { fetch } = createApifyFetch([{ fixture: "error-401-fake-token", status: 401 }]);
    const { log, lines } = createTestLog();
    const error = await checkApifyToken({ token: TOKEN, fetch, now: () => NOW, log }).catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(AuthError);
    expect((error as Error).message).toBe(
      "Apify answered 401: user-or-token-not-found (User was not found or authentication token is not valid).",
    );
    expect(lines).toEqual([
      expect.objectContaining({ event: "upstream.http", status: "failed", errorClass: "AuthError", httpStatus: 401 }),
    ]);
  });

  it("Apify out of reach: UpstreamUnavailableError; past its time: UpstreamTimeoutError", async () => {
    const refusing = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const { log } = createTestLog();
    await expect(checkApifyToken({ token: TOKEN, fetch: refusing, now: () => NOW, log })).rejects.toBeInstanceOf(
      UpstreamUnavailableError,
    );
    await expect(
      checkApifyToken({ token: TOKEN, fetch: hangingFetch, now: () => NOW, log, signal: AbortSignal.timeout(20) }),
    ).rejects.toBeInstanceOf(UpstreamTimeoutError);
  });
});
