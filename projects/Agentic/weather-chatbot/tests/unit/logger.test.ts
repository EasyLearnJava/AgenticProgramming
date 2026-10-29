/*
 * tests/unit/logger.test.ts: what a log line holds: the build's fields, the level as a word, the time; a request's own
 * fields on its child; secrets redacted; and a failure at its class's level, with its cause.
 */
import { describe, expect, it } from "vitest";
import { ContractError, UnexpectedError, UpstreamTimeoutError } from "@/lib/errors";
import { logFailure, toLaneFields } from "@/lib/logger";
import { createTestLog } from "@/tests/stubs/log-stand-ins";

describe("createLogger", () => {
  it("writes one JSON object a line: the time, the level as a word, the build's environment, and the fields", () => {
    const { log, lines } = createTestLog();
    log.info({ event: "chat.done", steps: 3 });
    expect(lines).toHaveLength(1);
    expect(lines[0]).toEqual({ level: "info", ts: expect.any(String), env: "local", event: "chat.done", steps: 3 });
    expect(Number.isNaN(Date.parse(String(lines[0]?.ts)))).toBe(false);
  });

  it("puts a child's fields, a request id say, on every line it writes", () => {
    const { log, lines } = createTestLog();
    const child = log.child({ requestId: "iad1::abc-1730-7f3a9c01", route: "/api/chat" });
    child.info({ event: "chat.request" });
    child.warn({ event: "budget.exceeded" });
    expect(lines.map((line) => [line.level, line.requestId, line.route])).toEqual([
      ["info", "iad1::abc-1730-7f3a9c01", "/api/chat"],
      ["warn", "iad1::abc-1730-7f3a9c01", "/api/chat"],
    ]);
  });

  it("redacts anything that could hold a secret: a token, a key, an authorization or bypass header", () => {
    const { log, lines } = createTestLog();
    log.info({
      event: "upstream.http",
      token: "apify_api_x",
      apiKey: "AIza-x",
      headers: { authorization: "Bearer x", "x-vercel-protection-bypass": "s3cret" },
    });
    expect(lines[0]).toMatchObject({
      token: "[redacted]",
      apiKey: "[redacted]",
      headers: { authorization: "[redacted]", "x-vercel-protection-bypass": "[redacted]" },
    });
    expect(JSON.stringify(lines)).not.toMatch(/apify_api_x|AIza-x|Bearer x|s3cret/);
  });
});

describe("toLaneFields", () => {
  it("names the lane, its door and its auth", () => {
    expect(toLaneFields("mcp-no-auth")).toEqual({ lane: "mcp-no-auth", transport: "mcp", auth: "none" });
    expect(toLaneFields("rest-auth")).toEqual({ lane: "rest-auth", transport: "rest", auth: "bearer" });
  });
});

describe("logFailure", () => {
  it("logs at the class's level: the class, our message, whether to retry, and the cause's class and message", () => {
    const { log, lines } = createTestLog();
    const cause = new TypeError("fetch failed");
    logFailure(log, "tool.call", new UpstreamTimeoutError("Open-Meteo didn't answer within 3000 ms.", { cause }), {
      tool: "get_forecast",
    });
    expect(lines[0]).toMatchObject({
      level: "warn",
      event: "tool.call",
      tool: "get_forecast",
      status: "failed",
      errorClass: "UpstreamTimeoutError",
      message: "Open-Meteo didn't answer within 3000 ms.",
      isRetryable: true,
      causeClass: "TypeError",
      cause: "fetch failed",
    });
    expect(lines[0]).not.toHaveProperty("stack");
  });

  it("logs an error-level class at error, and a bug with where it happened, its stack's first lines", () => {
    const { log, lines } = createTestLog();
    logFailure(log, "chat.failed", new ContractError("Open-Meteo refused the request with 400."));
    const bug = new TypeError("Cannot read properties of undefined (reading 'days')");
    logFailure(log, "chat.failed", new UnexpectedError(bug.message, { cause: bug }));
    expect(lines.map((line) => line.level)).toEqual(["error", "error"]);
    expect(lines[0]).not.toHaveProperty("cause");
    expect(String(lines[1]?.stack)).toContain("TypeError: Cannot read properties of undefined");
    expect(String(lines[1]?.stack).split("\n").length).toBeLessThanOrEqual(8);
  });

  it("cuts a long cause to 300 characters", () => {
    const { log, lines } = createTestLog();
    const cause = new Error("x".repeat(1000));
    logFailure(log, "chat.failed", new UpstreamTimeoutError("Our MCP server didn't connect.", { cause }));
    expect(String(lines[0]?.cause)).toHaveLength(300);
  });
});
