/*
 * lib/upstream/apify.ts: the call to the Apify Actor behind the auth lanes, with fetch (PLAN.md 4.3): one POST to its
 * run-sync address, with our token in the Authorization header (never in the URL), the Actor's build, time and cost
 * pinned in the URL, and its dataset items back. Each run writes one upstream.http line. Nothing is cached or retried:
 * a run costs money, and the lane falls back instead.
 */
import "server-only";
import {
  APIFY_ACTOR_BUILD,
  APIFY_ACTOR_RUN_URL,
  APIFY_MAX_CHARGE_USD,
  APIFY_RUN_TIMEOUT_SECONDS,
  MAX_APIFY_DETAIL_CHARS,
} from "@/lib/constants";
import {
  AppError,
  AuthError,
  BudgetExceededError,
  ContractError,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import { type Logger, logger } from "@/lib/logger";
import type { ActorLocation, WireRequest } from "@/lib/types";
import { toAbortKind, toHost, toRetryAfterMs } from "@/lib/utils";

/** What the Actor takes: Apify's own three fields, nothing of ours. */
export type ActorRunInput = { locations: ActorLocation[]; forecastDays: number; mode: "daily" | "hourly" };

/** One run's answer: the Actor's items, the request as the wire view shows it, and when it came back. */
export type ActorRun = { items: unknown[]; request: WireRequest; fetchedAt: string };

/** What a run takes besides its input: the tool's abort signal (Stop, the tool's budget), and the request's logger. */
export type ApifyCallOptions = { signal?: AbortSignal; log?: Logger };

/** The client's one call: run the Actor and wait for its items. */
export type ApifyClient = { runActor: (input: ActorRunInput, options?: ApifyCallOptions) => Promise<ActorRun> };

type ApifyOptions = { token: string; fetch?: typeof fetch; now?: () => Date };

// The token as the wire view shows it: never the real one.
const MASKED_AUTHORIZATION = "Bearer <APIFY_TOKEN>";
const HTTP_OK = 200;
const HTTP_CREATED = 201;
const HTTP_UNAUTHORIZED = 401;
const HTTP_PAYMENT_REQUIRED = 402;
const HTTP_FORBIDDEN = 403;
const HTTP_REQUEST_TIMEOUT = 408;
const HTTP_TOO_MANY_REQUESTS = 429;
const HTTP_SERVER_ERROR = 500;

/** A run's request, as it goes out but with the token masked: what a chip's wire view and the compare view show. */
export function toActorRequest(input: ActorRunInput): WireRequest {
  const limits = new URLSearchParams({
    build: APIFY_ACTOR_BUILD,
    timeout: String(APIFY_RUN_TIMEOUT_SECONDS),
    maxTotalChargeUsd: String(APIFY_MAX_CHARGE_USD),
  });
  return {
    method: "POST",
    url: `${APIFY_ACTOR_RUN_URL}?${limits}`,
    headers: { authorization: MASKED_AUTHORIZATION, "content-type": "application/json" },
    body: JSON.stringify(input),
  };
}

/**
 * Apify's own words about a failed run, from its error body: the error's type, and for an account's problem (401,
 * 402, 403), its message too. Other messages can quote the input, so only their type is kept.
 */
async function toApifyDetail(response: Response): Promise<string> {
  const body: unknown = await response.json().catch(() => undefined);
  const error = typeof body === "object" && body !== null && "error" in body ? body.error : undefined;
  const { type, message } = (typeof error === "object" && error !== null ? error : {}) as {
    type?: unknown;
    message?: unknown;
  };
  const isAccountProblem = [HTTP_UNAUTHORIZED, HTTP_PAYMENT_REQUIRED, HTTP_FORBIDDEN].includes(response.status);
  const words = [
    typeof type === "string" ? type : "no error type",
    isAccountProblem && typeof message === "string" ? `(${message})` : "",
  ];
  return words.join(" ").trim().slice(0, MAX_APIFY_DETAIL_CHARS);
}

/** A failed run's status, as one of our classes (PLAN.md 9.2), with Apify's own words in our message. */
async function toStatusError(response: Response): Promise<AppError> {
  const detail = await toApifyDetail(response);
  const { status } = response;
  if (status === HTTP_UNAUTHORIZED || status === HTTP_FORBIDDEN) {
    return new AuthError(`Apify answered ${status}: ${detail}.`);
  }
  if (status === HTTP_PAYMENT_REQUIRED) {
    return new BudgetExceededError(`Apify answered 402: ${detail}.`);
  }
  if (status === HTTP_REQUEST_TIMEOUT) {
    return new UpstreamTimeoutError(`Apify stopped the run at its time limit (408): ${detail}.`);
  }
  if (status === HTTP_TOO_MANY_REQUESTS) {
    return new UpstreamRateLimitedError(
      `Apify answered 429: ${detail}.`,
      toRetryAfterMs(response.headers.get("retry-after")),
    );
  }
  if (status >= HTTP_SERVER_ERROR) {
    return new UpstreamUnavailableError(`Apify answered ${status}: ${detail}.`);
  }
  return new ContractError(`Apify refused the run with ${status}: ${detail}.`);
}

/** A run's items, from a successful answer: a JSON list, or a ContractError. */
async function toItems(response: Response): Promise<unknown[]> {
  if (response.status !== HTTP_OK && response.status !== HTTP_CREATED) {
    throw await toStatusError(response);
  }
  const body: unknown = await response.json().catch(() => {
    throw new ContractError("Apify's answer isn't JSON.");
  });
  if (!Array.isArray(body)) {
    throw new ContractError("Apify's answer isn't a list of items.");
  }
  return body;
}

/**
 * A failed run as one of our classes. The signal comes first, whatever was going on when it fired, reading the answer
 * included: a stop (passed on as it is), or past the budget. Then ours, as they are; anything else is no answer.
 */
function toRunError(error: unknown, signal: AbortSignal | undefined): unknown {
  const abortKind = toAbortKind(signal);
  if (abortKind === "stop") {
    return signal?.reason;
  }
  if (abortKind === "timeout") {
    return new UpstreamTimeoutError("Apify didn't answer within the tool's time budget.", { cause: error });
  }
  return error instanceof AppError ? error : new UpstreamUnavailableError("Apify can't be reached.", { cause: error });
}

/**
 * Makes a client for the Actor, with our token. Everything it uses comes in as an option, so the tests can pass
 * stand-ins.
 */
export function createApifyClient({
  token,
  fetch: fetchApify = fetch,
  now = () => new Date(),
}: ApifyOptions): ApifyClient {
  return {
    async runActor(input, { signal, log = logger } = {}) {
      // ① The request, as the wire view shows it; the real one carries the token instead of the mask.
      const request = toActorRequest(input);
      const startedAt = now().getTime();
      let httpStatus: number | undefined;
      const toHttpFields = () => ({
        event: "upstream.http",
        upstream: "apify",
        host: toHost(request.url),
        ms: now().getTime() - startedAt,
        attempts: 1,
        httpStatus,
      });
      try {
        // ② One POST, with the tool's abort signal; Apify stops the run itself at 18 s.
        const response = await fetchApify(request.url, {
          method: "POST",
          headers: { ...request.headers, authorization: `Bearer ${token}` },
          body: request.body,
          signal,
        });
        httpStatus = response.status;
        const items = await toItems(response);
        log.info({ ...toHttpFields(), status: "ok", items: items.length });
        return { items, request, fetchedAt: now().toISOString() };
      } catch (error) {
        // ③ A failure says only its class here (the lane's line says the rest); a stop isn't logged.
        const failure = toRunError(error, signal);
        if (toAbortKind(signal) !== "stop") {
          log.info({
            ...toHttpFields(),
            status: "failed",
            errorClass: failure instanceof Error ? failure.name : "unknown",
          });
        }
        throw failure;
      }
    },
  };
}
