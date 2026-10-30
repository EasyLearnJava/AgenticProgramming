/*
 * lib/config.ts: the app's settings. The only file that reads process.env as the app runs; every value is checked with
 * Zod. (BotID's switch is written into the app when it's built: lib/botid.ts.)
 */
import "server-only";
import { z } from "zod";

// ① What the app reads from the environment. Vercel sets the commit and the environment on deployments made from
// Git, the deployment's id and own addresses (its URL, its branch's, the project's production domain) on every
// deployment, and the bypass secret when the project's Protection Bypass for Automation is on; you set the Gemini key
// and Apify's token, in Vercel's project settings or in .env.local on a laptop, and LOG_LEVEL if you want more or fewer
// log lines.
const EnvSchema = z.object({
  VERCEL_GIT_COMMIT_SHA: z.string().optional(),
  VERCEL_ENV: z.enum(["production", "preview", "development"]).optional(),
  VERCEL_DEPLOYMENT_ID: z.string().optional(),
  VERCEL_URL: z.string().optional(),
  VERCEL_BRANCH_URL: z.string().optional(),
  VERCEL_PROJECT_PRODUCTION_URL: z.string().optional(),
  VERCEL_AUTOMATION_BYPASS_SECRET: z.string().optional(),
  GOOGLE_API_KEY: z.string().optional(),
  CHAT_MODEL: z.string().optional(),
  APIFY_TOKEN: z.string().optional(),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"]).optional(),
});

/** How much the app logs: pino's levels, from "fatal" (least) to "trace" (most), or "silent" (nothing). */
export type LogLevel = NonNullable<z.output<typeof EnvSchema>["LOG_LEVEL"]>;

export type Config = {
  build: { commit: string | undefined; environment: string };
  chat: { googleApiKey: string | undefined; model: string };
  mcp: { bypassSecret: string | undefined };
  apify: { token: string | undefined };
  deployment: { id: string | undefined; url: string | undefined; hosts: string[] };
  log: { level: LogLevel };
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
    mcp: { bypassSecret: parsed.VERCEL_AUTOMATION_BYPASS_SECRET },
    apify: { token: parsed.APIFY_TOKEN },
    deployment: {
      id: parsed.VERCEL_DEPLOYMENT_ID,
      url: parsed.VERCEL_URL,
      hosts: [parsed.VERCEL_URL, parsed.VERCEL_BRANCH_URL, parsed.VERCEL_PROJECT_PRODUCTION_URL].filter(
        (host): host is string => host !== undefined,
      ),
    },
    log: { level: parsed.LOG_LEVEL ?? "info" },
  };
}

// ③ Read once, when the server starts (for the static pages: when Vercel builds them).
export const config: Config = parseConfig(process.env);
