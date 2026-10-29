/*
 * lib/config.ts: the app's settings. The only file that reads process.env; every value is checked with Zod.
 */
import "server-only";
import { z } from "zod";

// ① What the app reads from the environment. Vercel sets both of these on deployments made from Git.
const EnvSchema = z.object({
  VERCEL_GIT_COMMIT_SHA: z.string().optional(),
  VERCEL_ENV: z.enum(["production", "preview", "development"]).optional(),
});

export type Config = {
  build: { commit: string | undefined; environment: string };
};

const SHORT_COMMIT_LENGTH = 7;

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
  };
}

// ③ Read once, when the server starts (for the static pages: when Vercel builds them).
export const config: Config = parseConfig(process.env);
