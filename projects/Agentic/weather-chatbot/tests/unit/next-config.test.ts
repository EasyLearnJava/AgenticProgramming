/*
 * tests/unit/next-config.test.ts: next.config.ts sends the security headers on every response (PLAN.md 9.4), the
 * Content Security Policy only reporting for now, and tells the page that BotID is off away from Vercel.
 */
import { describe, expect, it, vi } from "vitest";
import nextConfig from "@/next.config";

describe("next.config.ts", () => {
  it("sends the security headers on every response", async () => {
    const routes = await nextConfig.headers?.();
    expect(routes).toHaveLength(1);
    expect(routes?.[0]?.source).toBe("/:path*");
    const headers = Object.fromEntries((routes?.[0]?.headers ?? []).map(({ key, value }) => [key, value]));
    expect(headers).toMatchObject({
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "X-Frame-Options": "DENY",
      "Permissions-Policy": "camera=(), geolocation=(self), microphone=()",
    });
    const policy = headers["Content-Security-Policy-Report-Only"] ?? "";
    for (const rule of ["default-src 'self'", "connect-src 'self'", "frame-ancestors 'none'", "object-src 'none'"]) {
      expect(policy).toContain(rule);
    }
  });

  it("keeps BotID off away from Vercel, where no challenge is served", () => {
    expect(nextConfig.env).toEqual({ NEXT_PUBLIC_BOTID: "off" });
  });

  it("keeps BotID off on Vercel too, until real browsers pass its check (issue 111)", async () => {
    vi.stubEnv("VERCEL", "1");
    vi.resetModules();
    const { default: builtOnVercel } = await import("@/next.config");
    vi.unstubAllEnvs();
    expect(builtOnVercel.env).toEqual({ NEXT_PUBLIC_BOTID: "off" });
  });
});
