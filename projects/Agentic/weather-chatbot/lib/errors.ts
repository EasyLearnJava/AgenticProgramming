/*
 * lib/errors.ts: the error classes the app throws, one per kind of failure (PLAN.md 9.2), each with the plain sentence
 * the page shows for it. Step 5 adds the rest of the map: the request id, the log level, the fallback.
 */
import "server-only";
import { InvalidToolInputError, NoSuchToolError } from "ai";
import { OWN_ERROR_HEADER } from "@/lib/constants";

const MODEL_UNAVAILABLE_MESSAGE = "The assistant didn't answer. Please try again.";

/** Every error the app throws on purpose. `message` is ours and safe to log; `userMessage` is what the page shows. */
export class AppError extends Error {
  override readonly name: string = "AppError";
  readonly userMessage: string = MODEL_UNAVAILABLE_MESSAGE;
}

/** The chat request breaks a rule: too many messages, a message too long, an unknown lane. The message says which. */
export class InputError extends AppError {
  override readonly name = "InputError";
  override readonly userMessage = `That message can't be sent: ${this.message}`;
}

/** A setting the app needs isn't there, such as GOOGLE_API_KEY. */
export class ConfigError extends AppError {
  override readonly name = "ConfigError";
  override readonly userMessage = "The assistant isn't set up on this deployment yet.";
}

/** An outside API didn't answer within its time budget. */
export class UpstreamTimeoutError extends AppError {
  override readonly name = "UpstreamTimeoutError";
  override readonly userMessage = "The weather service took too long to answer. Please try again.";
}

/** An outside API couldn't be reached, or answered with a 5xx. */
export class UpstreamUnavailableError extends AppError {
  override readonly name = "UpstreamUnavailableError";
  override readonly userMessage = "The weather service can't be reached right now. Please try again in a minute.";
}

/** An outside API answered 429: too many requests. `retryAfterMs` is its Retry-After, when it sent one. */
export class UpstreamRateLimitedError extends AppError {
  override readonly name = "UpstreamRateLimitedError";
  override readonly userMessage = "The weather service is busy. Please try again in a minute.";
  readonly retryAfterMs: number | undefined;

  constructor(message: string, retryAfterMs: number | undefined) {
    super(message);
    this.retryAfterMs = retryAfterMs;
  }
}

/** An outside API refused our request, or answered in a shape we don't expect. */
export class ContractError extends AppError {
  override readonly name = "ContractError";
  override readonly userMessage = "The weather service answered in a way we didn't expect. Please try again later.";
}

const BAD_TOOL_CALL_MESSAGE = "The assistant called a weather tool the wrong way. Please try again.";

/** The sentence the page shows for an error: the class's own for ours, a general one for anything else. */
export function toUserMessage(error: unknown): string {
  if (error instanceof AppError) {
    return error.userMessage;
  }
  // The model asked for a tool that doesn't exist, or with input the tool doesn't accept.
  if (InvalidToolInputError.isInstance(error) || NoSuchToolError.isInstance(error)) {
    return BAD_TOOL_CALL_MESSAGE;
  }
  return MODEL_UNAVAILABLE_MESSAGE;
}

const HTTP_BAD_REQUEST = 400;
const HTTP_INTERNAL_ERROR = 500;
const HTTP_UNAVAILABLE = 503;

/** The HTTP status for a failure before the answer starts: 400 for a bad request, 503 when not set up, else 500. */
function toStatus(error: unknown): number {
  if (error instanceof InputError) {
    return HTTP_BAD_REQUEST;
  }
  return error instanceof ConfigError ? HTTP_UNAVAILABLE : HTTP_INTERNAL_ERROR;
}

/** A failure before the answer starts, as a plain sentence, marked as ours so the page shows it as it is. */
export function toErrorResponse(error: unknown): Response {
  return new Response(toUserMessage(error), {
    status: toStatus(error),
    headers: { "content-type": "text/plain; charset=utf-8", [OWN_ERROR_HEADER]: "1" },
  });
}
