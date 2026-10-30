/*
 * tests/unit/errors.test.ts: the error map (PLAN.md 9.2): each class's sentence, level and retry rule; which class any
 * failure becomes; and the ref an error's sentence carries.
 */
import { APICallError, InvalidToolInputError, MessageConversionError, NoSuchToolError, RetryError } from "ai";
import { describe, expect, it } from "vitest";
import {
  AbortedError,
  type AppError,
  AuthError,
  BadToolCallError,
  BudgetExceededError,
  ConfigError,
  ContractError,
  InputError,
  ModelError,
  toAppError,
  toAppErrorByName,
  toErrorResponse,
  toUserMessage,
  UnexpectedError,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";

const REQUEST_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";

/** A failed call to Gemini, as AI SDK reports it. */
function geminiError(statusCode: number): APICallError {
  return new APICallError({
    message: `Gemini answered ${statusCode}.`,
    url: "https://generativelanguage.googleapis.com/v1beta/models/gemini:streamGenerateContent",
    requestBodyValues: {},
    statusCode,
  });
}

describe("the error map", () => {
  it("gives each class its sentence, its log level, and whether trying again can help", () => {
    const rows = (errors: AppError[]) => errors.map((error) => [error.name, error.level, error.isRetryable]);
    expect(
      rows([
        new InputError("a message can't be empty."),
        new ConfigError("GOOGLE_API_KEY isn't set."),
        new UpstreamTimeoutError("Open-Meteo didn't answer within 3000 ms."),
        new UpstreamUnavailableError("Open-Meteo answered 503."),
        new UpstreamRateLimitedError("Open-Meteo answered 429.", undefined),
        new ContractError("Open-Meteo refused the request with 400."),
        new AuthError("Apify answered 401: user-or-token-not-found."),
        new BudgetExceededError("Apify answered 402: x402-payment-required."),
        new ModelError("Gemini answered 503."),
        new BadToolCallError("Invalid input for tool get_forecast."),
        new AbortedError("The request was stopped."),
        new UnexpectedError("x is undefined"),
      ]),
    ).toEqual([
      ["InputError", "info", false],
      ["ConfigError", "error", false],
      ["UpstreamTimeoutError", "warn", true],
      ["UpstreamUnavailableError", "warn", true],
      ["UpstreamRateLimitedError", "warn", true],
      ["ContractError", "error", false],
      ["AuthError", "error", false],
      ["BudgetExceededError", "warn", false],
      ["ModelError", "error", true],
      ["BadToolCallError", "warn", true],
      ["AbortedError", "info", false],
      ["UnexpectedError", "error", false],
    ]);
  });
});

describe("toAppError", () => {
  it("keeps our own errors as they are", () => {
    const ours = new UpstreamTimeoutError("Open-Meteo didn't answer within 3000 ms.");
    expect(toAppError(ours)).toBe(ours);
  });

  it("makes anything a stop, once the request's signal says so", () => {
    const controller = new AbortController();
    controller.abort(Object.assign(new Error("The browser closed the connection."), { name: "ResponseAborted" }));
    const error = toAppError(new Error("aborted"), controller.signal);
    expect(error).toBeInstanceOf(AbortedError);
    expect(error.cause).toBeInstanceOf(Error);
  });

  it("makes the model's bad tool call a BadToolCallError, in our own words, and Gemini's failures ModelError", () => {
    const badInput = new InvalidToolInputError({
      toolName: "get_forecast",
      toolInput: '{"latitude":48.8534123,"days":30}',
      cause: "days: too big",
    });
    const badCall = toAppError(badInput);
    expect([badCall.name, badCall.message, badCall.cause]).toEqual([
      "BadToolCallError",
      "The model's input didn't match the tool's input schema.",
      undefined,
    ]);
    expect(toAppError(new NoSuchToolError({ toolName: "get_tides" }))).toBeInstanceOf(BadToolCallError);
    // AI SDK hands the page a bad call's error as its text.
    expect(toAppError("AI_InvalidToolInputError: Invalid input for tool get_forecast")).toBeInstanceOf(
      BadToolCallError,
    );
    expect(toAppError("AI_NoSuchToolError: Model tried to call unavailable tool 'get_tides'.")).toBeInstanceOf(
      BadToolCallError,
    );
    expect(toAppError(geminiError(503))).toBeInstanceOf(ModelError);
    const retried = new RetryError({ message: "Failed after 3 attempts.", reason: "maxRetriesExceeded", errors: [] });
    expect(toAppError(retried)).toBeInstanceOf(ModelError);
  });

  it("keeps AI SDK's other errors, such as our messages failing to convert, as bugs", () => {
    const conversion = new MessageConversionError({ originalMessage: { role: "user", parts: [] }, message: "x" });
    expect(toAppError(conversion)).toBeInstanceOf(UnexpectedError);
  });

  it("makes anything else a bug, keeping it as the cause", () => {
    const bug = new TypeError("x is undefined");
    const error = toAppError(bug);
    expect([error.name, error.message, error.cause]).toEqual(["UnexpectedError", "x is undefined", bug]);
    expect(toAppError("a string was thrown").message).toBe("a string was thrown");
  });
});

describe("toUserMessage", () => {
  it("gives our sentence for each class, never the error's own text", () => {
    expect(toUserMessage(new UpstreamTimeoutError("Open-Meteo didn't answer within 3000 ms."), REQUEST_ID)).toBe(
      "The weather service took too long to answer. Please try again.",
    );
    expect(toUserMessage(new UpstreamUnavailableError("x"), REQUEST_ID)).toContain("can't be reached");
    expect(toUserMessage(new UpstreamRateLimitedError("x", undefined), REQUEST_ID)).toContain("busy");
    expect(toUserMessage(new InputError("it's over 2,000 characters."), REQUEST_ID)).toBe(
      "That message can't be sent: it's over 2,000 characters.",
    );
    const badInput = new InvalidToolInputError({ toolName: "get_forecast", toolInput: "{}", cause: "bad" });
    expect(toUserMessage(badInput, REQUEST_ID)).toBe(
      "The assistant called a weather tool the wrong way. Please try again.",
    );
  });

  it("ends an error's sentence with the ref, the request id's last 8 characters, so its log line can be found", () => {
    expect(toUserMessage(new ConfigError("GOOGLE_API_KEY isn't set."), REQUEST_ID)).toBe(
      "The assistant isn't set up on this deployment yet. (ref b1a0d9e8)",
    );
    expect(toUserMessage(geminiError(429), REQUEST_ID)).toBe(
      "The assistant didn't answer. Please try again. (ref b1a0d9e8)",
    );
    expect(toUserMessage(new TypeError("x is undefined"), REQUEST_ID)).toBe("Something went wrong. (ref b1a0d9e8)");
    expect(toUserMessage(new ContractError("x"), REQUEST_ID)).toContain("didn't expect. Please try again later. (ref");
  });
});

describe("toErrorResponse", () => {
  it("answers 400 for a bad request, 503 if the chat isn't set up, 500 for anything else, as plain text", async () => {
    const bad = toErrorResponse(new InputError("it's empty."), REQUEST_ID);
    expect([bad.status, bad.headers.get("content-type"), await bad.text()]).toEqual([
      400,
      "text/plain; charset=utf-8",
      "That message can't be sent: it's empty.",
    ]);
    expect(toErrorResponse(new ConfigError("GOOGLE_API_KEY isn't set."), REQUEST_ID).status).toBe(503);
    const unexpected = toErrorResponse(new TypeError("x is undefined"), REQUEST_ID);
    expect([unexpected.status, await unexpected.text()]).toEqual([500, "Something went wrong. (ref b1a0d9e8)"]);
  });

  it("marks every response as the chat's own, so the page can tell it from Vercel's, and gives the request id", () => {
    const response = toErrorResponse(new InputError("it's empty."), REQUEST_ID);
    expect(response.headers.get("x-nimbus-error")).toBe("1");
    expect(response.headers.get("x-request-id")).toBe(REQUEST_ID);
  });
});

describe("toAppErrorByName", () => {
  it("turns a class's name and message, as an MCP server sends them, back into that class", () => {
    const error = toAppErrorByName("UpstreamTimeoutError", "Open-Meteo didn't answer within 3000 ms.");
    expect(error).toBeInstanceOf(UpstreamTimeoutError);
    expect(error.message).toBe("Open-Meteo didn't answer within 3000 ms.");
    expect(toAppErrorByName("ContractError", "x")).toBeInstanceOf(ContractError);
    expect(toAppErrorByName("UpstreamRateLimitedError", "x")).toBeInstanceOf(UpstreamRateLimitedError);
  });

  it("gives an UnexpectedError for a name it doesn't know, or none", () => {
    expect(toAppErrorByName("UnexpectedError", "The weather tool failed unexpectedly.")).toBeInstanceOf(
      UnexpectedError,
    );
    expect(toAppErrorByName(undefined, "x").name).toBe("UnexpectedError");
  });
});
