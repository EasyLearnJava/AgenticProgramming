/*
 * next.config.ts: the Next.js settings for the weather chatbot.
 */
import type { NextConfig } from "next";

// The Content Security Policy: our own scripts, styles, images, fonts and requests only, and no framing (PLAN.md 9.4).
// Next.js's pages carry inline scripts and styles, hence 'unsafe-inline'. It only reports for now: it's enforced once
// the live site shows it blocks nothing we need, BotID's challenge script included (step 8).
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

// The headers on every response: the policy above, no guessing of content types, no full addresses sent to other
// sites, no framing, and the location for our own page only; no camera, and no microphone until step 13's voice input.
export const SECURITY_HEADERS = [
  { key: "Content-Security-Policy-Report-Only", value: CONTENT_SECURITY_POLICY },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), geolocation=(self), microphone=()" },
];

const nextConfig: NextConfig = {
  // ① Don't announce the framework in every response's headers.
  poweredByHeader: false,
  // ② Catch unsafe React patterns early, while developing.
  reactStrictMode: true,
  // ③ Don't let `next dev` write an AGENTS.md file into the project.
  agentRules: false,
  // ④ Tell the page and the route, when they're built, whether BotID runs: off everywhere for now, since real browsers
  // failed its check on the live site (issue 111). It would run on Vercel only, which serves BotID's challenge.
  env: { NEXT_PUBLIC_BOTID: "off" },
  // ⑤ The security headers, on every response.
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
