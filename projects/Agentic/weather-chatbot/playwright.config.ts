/*
 * playwright.config.ts: the end-to-end tests' settings: a desktop screen and a 360-pixel phone screen, against this
 * laptop's production build or, with BASE_URL, against a live deployment. Like every test setting, it reads its own
 * environment variables; lib/config.ts is the app's only reader.
 */
import { defineConfig } from "@playwright/test";

const LOCAL_PORT = 3107;
const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 360, height: 780 };

// ① BASE_URL points the tests at a live deployment; without it, they start this laptop's production build.
const baseUrl = process.env.BASE_URL ?? `http://localhost:${LOCAL_PORT}`;
const isCi = Boolean(process.env.CI);
// ② The browser: Playwright's own Chromium (`npx playwright install chromium`), or an installed one, such as "msedge".
const channel = process.env.E2E_BROWSER_CHANNEL;
// ③ A preview deployment sits behind Vercel's Deployment Protection; the project's bypass secret lets the tests in.
const bypassSecret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;

export default defineConfig({
  testDir: "tests/e2e",
  forbidOnly: isCi,
  reporter: isCi ? "github" : "list",
  use: {
    baseURL: baseUrl,
    ...(channel ? { channel } : {}),
    ...(bypassSecret ? { extraHTTPHeaders: { "x-vercel-protection-bypass": bypassSecret } } : {}),
    // A trace records every request's headers, so there's none while the bypass secret is set.
    trace: bypassSecret ? "off" : "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: DESKTOP } },
    { name: "phone", use: { viewport: PHONE, isMobile: true, hasTouch: true } },
  ],
  // ④ Serve the build that `npm run build` made, unless the tests run against a live URL.
  ...(process.env.BASE_URL
    ? {}
    : { webServer: { command: `npm run start -- -p ${LOCAL_PORT}`, url: baseUrl, reuseExistingServer: !isCi } }),
});
