/*
 * lib/errors.ts: the error map (PLAN.md 9.2): one class per kind of failure, each with the sentence the page shows, its
 * log level, and whether trying again can help; and toAppError(), which turns any failure into one of them, once.
 */
import "server-only";
import {
  APICallError,
  InvalidToolInputError,
  NoContentGeneratedError,
  NoOutputGeneratedError,
  NoSuchToolError,
  RetryError,
  StreamProviderError,
} from "ai";
import { OWN_ERROR_HEADER, REQUEST_ID_HEADER } from "@/lib/constants";
import { toAbortKind, toRef } from "@/lib/utils";

/**
 * A failure's log level (PLAN.md 9.1): info for the normal path (a refused message, a stop), warn for trouble we
 * handled, error for a failure the user saw or one we didn't expect; an error's sentence carries the ref.
 */
export type FailureLevel = "info" | "warn" | "error";

const MODEL_UNAVAILABLE_MESSAGE = "The assistant didn't answer. Please try again.";
// The names AI SDK gives a bad tool call's two errors. It hands the page a bad call's error as its text
// ("AI_NoSuchToolError: Model tried to call unavailable tool 'get_tides'..."), not as the error itself.
const INVALID_TOOL_INPUT_NAME = "AI_InvalidToolInputError";
const NO_SUCH_TOOL_NAME = "AI_NoSuchToolError";

/** Every failure, as the app handles it. `message` is ours and safe to log; `userMessage` is what the page shows. */
export abstract class AppError extends Error {
  override readonly name: string = "AppError";
  abstract readonly userMessage: string;
  abstract readonly level: FailureLevel;
  abstract readonly isRetryable: boolean;
}

/** The chat request breaks a rule: too many messages, a message too long, an unknown lane. The message says which. */
export class InputError extends AppError {
  override readonly name = "InputError";
  override readonly userMessage = `That message can't be sent: ${this.message}`;
  override readonly level = "info";
  override readonly isRetryable = false;
}

/** A setting the app needs isn't there, such as GOOGLE_API_KEY. */
export class ConfigError extends AppError {
  override readonly name = "ConfigError";
  override readonly userMessage = "The assistant isn't set up on this deployment yet.";
  override readonly level = "error";
  override readonly isRetryable = false;
}

/** An outside API didn't answer within its time budget. */
export class UpstreamTimeoutError extends AppError {
  override readonly name = "UpstreamTimeoutError";
  override readonly userMessage = "The weather service took too long to answer. Please try again.";
  override readonly level = "warn";
  override readonly isRetryable = true;
}

/** An outside API couldn't be reached, or answered with a 5xx. */
export class UpstreamUnavailableError extends AppError {
  override readonly name = "UpstreamUnavailableError";
  override readonly userMessage = "The weather service can't be reached right now. Please try again in a minute.";
  override readonly level = "warn";
  override readonly isRetryable = true;
}

/** An outside API answered 429: too many requests. `retryAfterMs` is its Retry-After, when it sent one. */
export class UpstreamRateLimitedError extends AppError {
  override readonly name = "UpstreamRateLimitedError";
  override readonly userMessage = "The weather service is busy. Please try again in a minute.";
  override readonly level = "warn";
  override readonly isRetryable = true;
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
  override readonly level = "error";
  override readonly isRetryable = false;
}

/** The model didn't answer: Gemini timed out, answered with a 5xx, or a 429 when the free tier's quota is used up. */
export class ModelError extends AppError {
  override readonly name = "ModelError";
  override readonly userMessage = MODEL_UNAVAILABLE_MESSAGE;
  override readonly level = "error";
  override readonly isRetryable = true;
}

/** The model called a tool that doesn't exist, or with input the tool doesn't take; it's told, and can try again. */
export class BadToolCallError extends AppError {
  override readonly name = "BadToolCallError";
  override readonly userMessage = "The assistant called a weather tool the wrong way. Please try again.";
  override readonly level = "warn";
  override readonly isRetryable = true;
}

/** The user pressed Stop, or closed the page: nothing failed, and the page shows no error. */
export class AbortedError extends AppError {
  override readonly name = "AbortedError";
  override readonly userMessage = "Stopped.";
  override readonly level = "info";
  override readonly isRetryable = false;
}

/** Anything else: a bug. The page says only that something went wrong, with the ref, so its log line can be found. */
export class UnexpectedError extends AppError {
  override readonly name = "UnexpectedError";
  override readonly userMessage = "Something went wrong.";
  override readonly level = "error";
  override readonly isRetryable = false;
}

/** AI SDK's name for a bad tool call's error, from the error or from its text; undefined for anything else. */
function toBadToolCallName(error: unknown): string | undefined {
  if (InvalidToolInputError.isInstance(error) || NoSuchToolError.isInstance(error)) {
    return error.name;
  }
  return typeof error === "string"
    ? [INVALID_TOOL_INPUT_NAME, NO_SUCH_TOOL_NAME].find((name) => error.startsWith(`${name}:`))
    : undefined;
}

/**
 * Whether a failure is the model's own, as AI SDK reports it: Gemini's HTTP error, AI SDK's retries giving up on it,
 * an error inside its stream, or no answer at all. Other AI SDK errors (our messages failing to convert, say) are bugs.
 */
function isModelFailure(error: unknown): boolean {
  return (
    APICallError.isInstance(error) ||
    RetryError.isInstance(error) ||
    StreamProviderError.isInstance(error) ||
    NoOutputGeneratedError.isInstance(error) ||
    NoContentGeneratedError.isInstance(error)
  );
}

/**
 * Any failure as one of our classes: ours as it is; anything once the request's signal says stop; the model's bad tool
 * call; the model's own failures; and anything else, which is a bug. The original is kept as the cause, except for a
 * bad tool call: AI SDK's message for it quotes the model's input, which can hold a place or exact coordinates.
 */
export function toAppError(error: unknown, signal?: AbortSignal): AppError {
  if (error instanceof AppError) {
    return error;
  }
  if (toAbortKind(signal) === "stop") {
    return new AbortedError("The request was stopped.", { cause: error });
  }
  const badCall = toBadToolCallName(error);
  if (badCall !== undefined) {
    return new BadToolCallError(
      badCall === NO_SUCH_TOOL_NAME
        ? "The model called a tool that doesn't exist."
        : "The model's input didn't match the tool's input schema.",
    );
  }
  if (isModelFailure(error)) {
    return new ModelError(error instanceof Error ? error.message : String(error), { cause: error });
  }
  return new UnexpectedError(error instanceof Error ? error.message : String(error), { cause: error });
}

/**
 * One of our errors, from its class's name and message, as an MCP server sends a failed tool's; a name it doesn't
 * know is an UnexpectedError. The names are the classes' own `name` fields, which minifying the code can't change.
 */
export function toAppErrorByName(name: string | undefined, message: string): AppError {
  switch (name) {
    case "InputError":
      return new InputError(message);
    case "ConfigError":
      return new ConfigError(message);
    case "UpstreamTimeoutError":
      return new UpstreamTimeoutError(message);
    case "UpstreamUnavailableError":
      return new UpstreamUnavailableError(message);
    case "UpstreamRateLimitedError":
      return new UpstreamRateLimitedError(message, undefined);
    case "ContractError":
      return new ContractError(message);
    default:
      return new UnexpectedError(message);
  }
}

/**
 * The sentence the page shows for a failure: its class's own, never the error's text; with the ref (the request id's
 * last 8 characters) when it's logged as an error, so its log line can be found.
 */
export function toUserMessage(error: unknown, requestId: string): string {
  const appError = toAppError(error);
  return appError.level === "error" ? `${appError.userMessage} (ref ${toRef(requestId)})` : appError.userMessage;
}

const HTTP_BAD_REQUEST = 400;
const HTTP_INTERNAL_ERROR = 500;
const HTTP_UNAVAILABLE = 503;

/** The HTTP status for a failure before the answer starts: 400 for a bad request, 503 when not set up, else 500. */
function toStatus(error: AppError): number {
  if (error instanceof InputError) {
    return HTTP_BAD_REQUEST;
  }
  return error instanceof ConfigError ? HTTP_UNAVAILABLE : HTTP_INTERNAL_ERROR;
}

/** A failure before the answer starts, as a plain sentence, marked as ours so the page shows it, with the request id. */
export function toErrorResponse(error: unknown, requestId: string): Response {
  const appError = toAppError(error);
  return new Response(toUserMessage(appError, requestId), {
    status: toStatus(appError),
    headers: {
      "content-type": "text/plain; charset=utf-8",
      [OWN_ERROR_HEADER]: "1",
      [REQUEST_ID_HEADER]: requestId,
    },
  });
}
