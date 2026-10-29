/*
 * tests/unit/chat/model.test.ts: the chat model needs GOOGLE_API_KEY, and says so before any call is made.
 */
import { describe, expect, it } from "vitest";
import { getChatModel } from "@/lib/chat/model";
import { ConfigError } from "@/lib/errors";

describe("getChatModel", () => {
  it("throws ConfigError without a key, so the page can say the chat isn't set up", () => {
    expect(() => getChatModel({ googleApiKey: undefined, model: "gemini-3.5-flash-lite" })).toThrow(ConfigError);
  });

  it("makes the Gemini model the settings name, without calling it", () => {
    const model = getChatModel({ googleApiKey: "not-a-real-key", model: "gemini-3.5-flash-lite" });
    expect(typeof model === "object" && model.modelId).toBe("gemini-3.5-flash-lite");
  });
});
