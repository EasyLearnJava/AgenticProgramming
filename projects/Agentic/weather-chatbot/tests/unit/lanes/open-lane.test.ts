/*
 * tests/unit/lanes/open-lane.test.ts: where the MCP lane finds this deployment's /api/mcp: never at an address the
 * request made up.
 */
import { describe, expect, it } from "vitest";
import { toAvailableLaneIds, toSelfOrigin } from "@/lib/lanes/open-lane";

const ON_VERCEL = {
  id: "dpl_abc123",
  url: "weather-chatbot-abc123-silverado.vercel.app",
  hosts: [
    "weather-chatbot-abc123-silverado.vercel.app",
    "weather-chatbot-git-main-silverado.vercel.app",
    "weather-chatbot-hazel.vercel.app",
  ],
};

describe("toSelfOrigin", () => {
  it("on Vercel, uses the address the request came to, when it's one of the deployment's own", () => {
    expect(toSelfOrigin("https://weather-chatbot-hazel.vercel.app/api/chat", ON_VERCEL)).toBe(
      "https://weather-chatbot-hazel.vercel.app",
    );
    expect(toSelfOrigin("https://weather-chatbot-git-main-silverado.vercel.app/api/chat", ON_VERCEL)).toBe(
      "https://weather-chatbot-git-main-silverado.vercel.app",
    );
  });

  it("on Vercel, uses the deployment's own URL for any other address, such as a forged Host header", () => {
    expect(toSelfOrigin("https://attacker.example/api/chat", ON_VERCEL)).toBe(
      "https://weather-chatbot-abc123-silverado.vercel.app",
    );
  });

  it("off Vercel (a laptop), uses the request's own origin", () => {
    expect(toSelfOrigin("http://localhost:3000/api/chat", { id: undefined, url: undefined, hosts: [] })).toBe(
      "http://localhost:3000",
    );
  });
});

describe("toAvailableLaneIds", () => {
  it("runs both no-auth lanes anywhere, and REST · with auth only where Apify's token is set", () => {
    expect(toAvailableLaneIds(undefined)).toEqual(["rest-no-auth", "mcp-no-auth"]);
    expect(toAvailableLaneIds("test-token-not-real")).toEqual(["rest-no-auth", "mcp-no-auth", "rest-auth"]);
  });
});
