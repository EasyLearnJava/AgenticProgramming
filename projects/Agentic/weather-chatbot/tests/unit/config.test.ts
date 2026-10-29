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
});
