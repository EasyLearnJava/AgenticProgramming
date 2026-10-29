/*
 * lib/config.ts: the app's settings. The only file that reads process.env; every value is checked with Zod.
 */
import "server-only";
import { z } from "zod";

// ① What the app reads from the environment. Vercel sets the first two on deployments made from Git; you set the
// Gemini key, in Vercel's project settings or in .env.local on a laptop.
const EnvSchema = z.object({
  VERCEL_GIT_COMMIT_SHA: z.string().optional(),
  VERCEL_ENV: z.enum(["production", "preview", "development"]).optional(),
  GOOGLE_API_KEY: z.string().optional(),
  CHAT_MODEL: z.string().optional(),
});

export type Config = {
  build: { commit: string | undefined; environment: string };
  chat: { googleApiKey: string | undefined; model: string };
};

const SHORT_COMMIT_LENGTH = 7;
const DEFAULT_CHAT_MODEL = "gemini-3.5-flash-lite";

/** Drops the variables whose value is empty, so "" counts as missing (`vercel env pull` writes some that way). */
function dropEmptyValues(env: Record<string, string | undefined>): Record<string, string> {
  return Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => Boolean(entry[1])));
}

/** Turns the environment into the app's settings; throws if a value is malformed. */
export function parseConfig(env: Record<string, string | undefined>): Config {
  // ② Check the values that are set, then shape them the way the app uses them.
  const parsed = EnvSchema.parse(dropEmptyValues(env));
  return {
    build: {
      commit: parsed.VERCEL_GIT_COMMIT_SHA?.slice(0, SHORT_COMMIT_LENGTH),
      environment: parsed.VERCEL_ENV ?? "local",
    },
    chat: { googleApiKey: parsed.GOOGLE_API_KEY, model: parsed.CHAT_MODEL ?? DEFAULT_CHAT_MODEL },
  };
}

// ③ Read once, when the server starts (for the static pages: when Vercel builds them).
export const config: Config = parseConfig(process.env);
