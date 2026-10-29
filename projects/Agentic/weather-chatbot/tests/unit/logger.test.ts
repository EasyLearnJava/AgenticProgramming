/*
 * tests/unit/logger.test.ts: a failure is logged as one JSON line, with its class and message.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { UpstreamTimeoutError } from "@/lib/errors";
import { logError } from "@/lib/logger";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("logError", () => {
  it("writes one JSON line: the level, the event, the fields, the error's class and message", () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    logError("tool.failed", new UpstreamTimeoutError("Open-Meteo didn't answer within 3000 ms."), {
      tool: "get_forecast",
    });
    expect(written).toHaveBeenCalledOnce();
    expect(JSON.parse(String(written.mock.calls[0]?.[0]))).toEqual({
      level: "error",
      event: "tool.failed",
      tool: "get_forecast",
      errorClass: "UpstreamTimeoutError",
      message: "Open-Meteo didn't answer within 3000 ms.",
    });
  });

  it("logs something that isn't an Error as text", () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    logError("chat.failed", "a string was thrown");
    expect(JSON.parse(String(written.mock.calls[0]?.[0]))).toMatchObject({
      errorClass: "NonError",
      message: "a string was thrown",
    });
  });
});
