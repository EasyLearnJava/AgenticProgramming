/*
 * tests/unit/errors.test.ts: the sentence the page shows for each error.
 */
import { InvalidToolInputError, NoSuchToolError } from "ai";
import { describe, expect, it } from "vitest";
import {
  ConfigError,
  ContractError,
  InputError,
  toErrorResponse,
  toUserMessage,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";

describe("toUserMessage", () => {
  it("gives our sentence for each of our classes, never the error's own text", () => {
    expect(toUserMessage(new ConfigError("GOOGLE_API_KEY isn't set."))).toBe(
      "The assistant isn't set up on this deployment yet.",
    );
    expect(toUserMessage(new UpstreamTimeoutError("Open-Meteo didn't answer within 3000 ms."))).toBe(
      "The weather service took too long to answer. Please try again.",
    );
    expect(toUserMessage(new UpstreamUnavailableError("Open-Meteo answered 503."))).toContain("can't be reached");
    expect(toUserMessage(new UpstreamRateLimitedError("Open-Meteo answered 429.", undefined))).toContain("busy");
    expect(toUserMessage(new ContractError("Open-Meteo refused the request with 400."))).toContain("didn't expect");
  });

  it("says which rule an input broke", () => {
    expect(toUserMessage(new InputError("it's over 2,000 characters."))).toBe(
      "That message can't be sent: it's over 2,000 characters.",
    );
  });

  it("gives a general sentence for anything else, such as the model failing", () => {
    expect(toUserMessage(new Error("503 Service Unavailable from the model"))).toBe(
      "The assistant didn't answer. Please try again.",
    );
  });
});

describe("toErrorResponse", () => {
  it("answers 400 for a bad request, 503 when the chat isn't set up, and 500 for anything else, in plain text", async () => {
    const bad = toErrorResponse(new InputError("it's empty."));
    expect([bad.status, bad.headers.get("content-type"), await bad.text()]).toEqual([
      400,
      "text/plain; charset=utf-8",
      "That message can't be sent: it's empty.",
    ]);
    expect(toErrorResponse(new ConfigError("GOOGLE_API_KEY isn't set.")).status).toBe(503);
    const unexpected = toErrorResponse(new TypeError("x is undefined"));
    expect([unexpected.status, await unexpected.text()]).toEqual([
      500,
      "The assistant didn't answer. Please try again.",
    ]);
  });

  it("marks every response as the chat's own, so the page can tell it from Vercel's error pages", () => {
    expect(toErrorResponse(new InputError("it's empty.")).headers.get("x-nimbus-error")).toBe("1");
    expect(toErrorResponse(new TypeError("x is undefined")).headers.get("x-nimbus-error")).toBe("1");
  });
});

describe("toUserMessage, for the model's own mistakes", () => {
  it("says a tool was called the wrong way, for a bad input or a tool that doesn't exist", () => {
    const sentence = "The assistant called a weather tool the wrong way. Please try again.";
    const badInput = new InvalidToolInputError({ toolName: "get_forecast", toolInput: "{}", cause: "bad" });
    expect(toUserMessage(badInput)).toBe(sentence);
    expect(toUserMessage(new NoSuchToolError({ toolName: "get_tides" }))).toBe(sentence);
  });
});
