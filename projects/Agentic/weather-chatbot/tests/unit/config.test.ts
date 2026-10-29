/*
 * tests/unit/config.test.ts: lib/config.ts turns the environment into settings, and rejects malformed values.
 */
import { describe, expect, it } from "vitest";
import { parseConfig } from "@/lib/config";

describe("parseConfig", () => {
  it("shortens the commit Vercel built to 7 characters", () => {
    const config = parseConfig({ VERCEL_GIT_COMMIT_SHA: "15c022c1a2b3c4d5e6f7", VERCEL_ENV: "production" });
    expect(config.build).toEqual({ commit: "15c022c", environment: "production" });
  });

  it("calls a run without Vercel's variables local", () => {
    expect(parseConfig({}).build).toEqual({ commit: undefined, environment: "local" });
  });

  it("treats empty values as missing, as `vercel env pull` writes them", () => {
    expect(parseConfig({ VERCEL_GIT_COMMIT_SHA: "", VERCEL_ENV: "" }).build).toEqual({
      commit: undefined,
      environment: "local",
    });
  });

  it("rejects an environment name Vercel doesn't use", () => {
    expect(() => parseConfig({ VERCEL_ENV: "staging" })).toThrow();
  });

  it("uses gemini-3.5-flash-lite unless CHAT_MODEL names another model, and has no key unless one is set", () => {
    expect(parseConfig({}).chat).toEqual({ googleApiKey: undefined, model: "gemini-3.5-flash-lite" });
    expect(parseConfig({ GOOGLE_API_KEY: "", CHAT_MODEL: "" }).chat).toEqual({
      googleApiKey: undefined,
      model: "gemini-3.5-flash-lite",
    });
    expect(parseConfig({ GOOGLE_API_KEY: "test-key", CHAT_MODEL: "gemini-other" }).chat).toEqual({
      googleApiKey: "test-key",
      model: "gemini-other",
    });
  });

  it("lists the deployment's id and own addresses Vercel sets, and none off Vercel", () => {
    expect(parseConfig({}).deployment).toEqual({ id: undefined, url: undefined, hosts: [] });
    expect(
      parseConfig({
        VERCEL_DEPLOYMENT_ID: "dpl_abc123",
        VERCEL_URL: "weather-chatbot-abc123-silverado.vercel.app",
        VERCEL_BRANCH_URL: "weather-chatbot-git-main-silverado.vercel.app",
        VERCEL_PROJECT_PRODUCTION_URL: "weather-chatbot-hazel.vercel.app",
      }).deployment,
    ).toEqual({
      id: "dpl_abc123",
      url: "weather-chatbot-abc123-silverado.vercel.app",
      hosts: [
        "weather-chatbot-abc123-silverado.vercel.app",
        "weather-chatbot-git-main-silverado.vercel.app",
        "weather-chatbot-hazel.vercel.app",
      ],
    });
  });

  it("logs at info unless LOG_LEVEL says otherwise, and refuses a level pino doesn't have", () => {
    expect(parseConfig({}).log.level).toBe("info");
    expect(parseConfig({ LOG_LEVEL: "silent" }).log.level).toBe("silent");
    expect(() => parseConfig({ LOG_LEVEL: "loud" })).toThrow();
  });

  it("reads the bypass secret Vercel sets for Protection Bypass for Automation, when it's there", () => {
    expect(parseConfig({}).mcp).toEqual({ bypassSecret: undefined });
    expect(parseConfig({ VERCEL_AUTOMATION_BYPASS_SECRET: "test-secret" }).mcp).toEqual({
      bypassSecret: "test-secret",
    });
  });
});
