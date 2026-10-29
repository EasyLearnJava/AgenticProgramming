/*
 * next.config.ts: the Next.js settings for the weather chatbot.
 */
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ① Don't announce the framework in every response's headers.
  poweredByHeader: false,
  // ② Catch unsafe React patterns early, while developing.
  reactStrictMode: true,
  // ③ Don't let `next dev` write an AGENTS.md file into the project.
  agentRules: false,
};

export default nextConfig;
