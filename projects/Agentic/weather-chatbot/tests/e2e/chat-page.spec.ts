/*
 * tests/e2e/chat-page.spec.ts: the chat page in a real browser. /api/chat is answered in the browser with a recorded
 * answer (tests/e2e/chat-stream.ts), so no model is called, here or against a live URL: the welcome, the lanes, an
 * answer with its chips and weather card, an auth lane's fallback, a failure, Stop, the location pin, the nearby city,
 * the compare view, accessibility (axe) and a 360-pixel screen. REST · with auth runs only where the deployment has
 * Apify's token, so the tests read from the picker which it is, and check the page says the same everywhere.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import {
  ANSWER,
  CUT_SHORT_STREAM_BODY,
  FALLBACK_PARIS_STREAM_BODY,
  FALLBACK_SENTENCE,
  FORECAST_URL,
  LEAK_IMAGE_URL,
  MARKDOWN_STREAM_BODY,
  MCP_PARIS_STREAM_BODY,
  MCP_URL,
  PARIS_STREAM_BODY,
  STREAM_HEADERS,
} from "@/tests/e2e/chat-stream";

const PARIS_QUESTION = "Do I need an umbrella in Paris tomorrow afternoon?";
// REST · with auth's request: the Apify Actor's run, with its build, time and cost in the URL.
const ACTOR_RUN_URL =
  "https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items" +
  "?build=1.0.9&timeout=18&maxTotalChargeUsd=0.01";

/** Whether this deployment runs REST · with auth, as its picker says: it does only with Apify's token. */
async function hasApifyToken(page: Page): Promise<boolean> {
  return page.getByLabel(/REST · with auth/).isEnabled();
}

/** Answers the page's /api/chat with the recorded Paris answer, and keeps each request body it sent. */
async function answerWithParis(page: Page): Promise<unknown[]> {
  const bodies: unknown[] = [];
  await page.route("**/api/chat", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, headers: STREAM_HEADERS, body: PARIS_STREAM_BODY });
  });
  return bodies;
}

/** Asks the Paris question, from the welcome's questions to try, and waits for the answer. */
async function askParis(page: Page): Promise<void> {
  await page.getByRole("button", { name: PARIS_QUESTION }).click();
  // In the conversation: the same words are also in the hidden announcement for screen readers.
  await expect(page.getByRole("list", { name: "Conversation" }).getByText(ANSWER)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  // A test that doesn't answer /api/chat itself gets a failed request, never the real model; a later route wins.
  await page.route("**/api/chat", (route) => route.abort());
  // No nearby city unless a test gives one: on a laptop there's none anyway.
  await page.route("**/api/nearby-city", (route) => route.fulfill({ json: { city: null } }));
  await page.goto("/");
});

test("shows the welcome and the questions to try, with the menu and the build line", async ({ page }) => {
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(/^Hi, I’m Nimbus/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Questions to try" }).getByRole("button")).toHaveCount(3);
  await expect(page.getByText(/^Build/)).toBeVisible();
});

test("starts on MCP · no auth, the default; both auth lanes run only with Apify's token", async ({ page }) => {
  await expect(page.getByLabel(/MCP · no auth/)).toBeChecked();
  await expect(page.getByLabel(/REST · no auth/)).toBeEnabled();
  const stateOf = (label: RegExp) =>
    page.locator(".lane-option", { has: page.getByLabel(label) }).locator(".lane-option-step");
  const authState = (await hasApifyToken(page)) ? "live" : "needs an Apify token";
  await expect(stateOf(/REST · with auth/)).toHaveText(authState);
  await expect(stateOf(/MCP · with auth/)).toHaveText(authState);
});

test("moves between the lanes this deployment runs with the arrow keys, skipping the ones that wait", async ({
  page,
}) => {
  // In the grid's order, the lane before MCP · no auth is REST · with auth, when it runs here.
  const before = (await hasApifyToken(page)) ? /REST · with auth/ : /REST · no auth/;
  const mcpNoAuth = page.getByLabel(/MCP · no auth/);
  await mcpNoAuth.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByLabel(before)).toBeChecked();
  await page.keyboard.press("ArrowRight");
  await expect(mcpNoAuth).toBeChecked();
});

test("answers through MCP · no auth: each chip says so, and shows its JSON-RPC request", async ({ page }) => {
  const bodies: unknown[] = [];
  await page.route("**/api/chat", async (route) => {
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, headers: STREAM_HEADERS, body: MCP_PARIS_STREAM_BODY });
  });
  await askParis(page);
  expect(bodies[0]).toMatchObject({ laneId: "mcp-no-auth" });
  const chips = page.locator("details.tool-chip");
  await expect(chips.nth(0).locator("summary")).toContainText(
    "MCP · no auth · weather-chatbot-hazel.vercel.app · 0.6 s",
  );
  // The forecast came from the server's cache: the call still went out, and the chip says so, with its time.
  await expect(chips.nth(1).locator("summary")).toContainText(
    "MCP · no auth · weather-chatbot-hazel.vercel.app · 0.1 s · cached",
  );
  await chips.nth(1).locator("summary").click();
  await expect(chips.nth(1).getByText(/Our MCP server answered from its cache: this request went out/)).toBeVisible();
  await expect(chips.nth(1).getByText(`POST ${MCP_URL}`)).toBeVisible();
  await expect(chips.nth(1).getByText(/"method":"tools\/call"/)).toBeVisible();
});

test("answers: two chips with their lane and request, the answer, and the weather card", async ({ page }) => {
  const bodies = await answerWithParis(page);
  await page.getByLabel(/REST · no auth/).check();
  await askParis(page);
  // The request carried the lane and the browser's locale.
  expect(bodies[0]).toMatchObject({ laneId: "rest-no-auth", messages: [{ role: "user" }] });
  expect(typeof (bodies[0] as { locale?: unknown }).locale).toBe("string");
  expect(typeof (bodies[0] as { timeZone?: unknown }).timeZone).toBe("string");
  // Each chip says which lane and host it went through, and how long it took.
  const chips = page.locator("details.tool-chip");
  await expect(chips).toHaveCount(2);
  await expect(chips.nth(0).locator("summary")).toContainText("REST · no auth · geocoding-api.open-meteo.com · 0.3 s");
  await expect(chips.nth(1).locator("summary")).toContainText("48.85, 2.35 · 2 days, hourly");
  // A chip opens to show the request exactly as it went out.
  const forecastChip = chips.nth(1);
  await expect(forecastChip).not.toHaveAttribute("open");
  await forecastChip.locator("summary").click();
  await expect(forecastChip).toHaveAttribute("open", "");
  await expect(forecastChip.getByText(`GET ${FORECAST_URL}`)).toBeVisible();
  // The weather card names the place geocoding found, with a row per day.
  const card = page.getByRole("region", { name: "Forecast for Paris, Île-de-France Region, France" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Friday 30")).toBeVisible();
  await expect(card.getByText("6 to 15 °C")).toBeVisible();
});

test("says on the chip when REST · with auth fell back, and shows the forecast it got instead", async ({ page }) => {
  // A recorded answer: the page shows a tool call's lane from its result, whichever lane is picked.
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 200, headers: STREAM_HEADERS, body: FALLBACK_PARIS_STREAM_BODY }),
  );
  await askParis(page);
  const chips = page.locator("details.tool-chip");
  await expect(chips.nth(0).locator("summary")).toContainText("REST · with auth · geocoding-api.open-meteo.com");
  const forecastSummary = chips.nth(1).locator("summary");
  await expect(forecastSummary).toContainText("gochujang--open-meteo-weather-forecast");
  await expect(forecastSummary).toContainText("48.85, 2.35 · 2 days, hourly");
  // The call says which lane answered, and the sentence says why, with the ref to find its log line.
  await expect(forecastSummary).toContainText("REST · no auth · api.open-meteo.com");
  await expect(forecastSummary.locator(".tool-chip-fallback")).toHaveText(`! ${FALLBACK_SENTENCE}`);
  await expect(page.getByRole("region", { name: "Forecast for Paris, Île-de-France Region, France" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("shows the server's sentence when the chat can't answer, with its ref and Try again", async ({ page }) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      status: 503,
      contentType: "text/plain",
      headers: { "x-nimbus-error": "1", "x-request-id": "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8" },
      body: "The assistant isn't set up on this deployment yet. (ref b1a0d9e8)",
    }),
  );
  await page.getByRole("button", { name: PARIS_QUESTION }).click();
  // Ours: Next.js's route announcer is an alert too.
  const alert = page.getByRole("alert").filter({ hasText: "isn't set up" });
  await expect(alert).toContainText("The assistant isn't set up on this deployment yet. (ref b1a0d9e8)");
  await expect(alert.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("turns Send into Stop while an answer is on its way, and Stop ends it", async ({ page }) => {
  // The answer is held back until Stop has been pressed, then the request is dropped.
  let release = (): void => undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/chat", async (route) => {
    await held;
    await route.abort().catch(() => undefined);
  });
  await page.getByRole("button", { name: PARIS_QUESTION }).click();
  await expect(page.getByText("Nimbus is checking the weather…")).toBeVisible();
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  await expect(page.getByText("Nimbus is checking the weather…")).toBeHidden();
  release();
});

test("says when a time budget cut an answer short, and shows its unfinished tool call as stopped", async ({ page }) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 200, headers: STREAM_HEADERS, body: CUT_SHORT_STREAM_BODY }),
  );
  await page.getByRole("button", { name: PARIS_QUESTION }).click();
  await expect(page.getByText(/This answer was cut short/)).toBeVisible();
  const chip = page.locator("details.tool-chip");
  await expect(chip).toHaveClass(/tool-chip-stopped/);
  await expect(chip.locator("summary")).toContainText("Stopped:");
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
});

test("never shows or fetches an image from an answer's Markdown, and opens its links in a new tab", async ({
  page,
}) => {
  const requested: string[] = [];
  page.on("request", (request) => requested.push(request.url()));
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 200, headers: STREAM_HEADERS, body: MARKDOWN_STREAM_BODY }),
  );
  await page.getByRole("button", { name: PARIS_QUESTION }).click();
  const conversation = page.getByRole("list", { name: "Conversation" });
  await expect(conversation.getByText("Sunny in Paris.")).toBeVisible();
  await expect(conversation.locator("img")).toHaveCount(0);
  const link = conversation.getByRole("link", { name: "Open-Meteo" });
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(requested.filter((url) => url.startsWith(new URL(LEAK_IMAGE_URL).origin))).toEqual([]);
});

test("shows one plain sentence for an error page that isn't the chat's own", async ({ page }) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 504, contentType: "text/plain", body: "FUNCTION_INVOCATION_TIMEOUT iad1::abc123" }),
  );
  await page.getByRole("button", { name: PARIS_QUESTION }).click();
  const alert = page.getByRole("alert").filter({ hasText: "couldn't be reached" });
  await expect(alert).toContainText("The chat couldn't be reached. Please try again.");
  await expect(page.getByText(/FUNCTION_INVOCATION_TIMEOUT/)).toHaveCount(0);
});

test("starts a new chat: the conversation goes, and the welcome comes back", async ({ page }) => {
  await answerWithParis(page);
  await askParis(page);
  await page.getByRole("button", { name: "New chat" }).click();
  await expect(page.getByText(/^Hi, I’m Nimbus/)).toBeVisible();
  await expect(page.locator("details.tool-chip")).toHaveCount(0);
});

test("suggests a question about the nearby city, saying it's only a guess", async ({ page }) => {
  await page.route("**/api/nearby-city", (route) => route.fulfill({ json: { city: "Dallas" } }));
  await page.reload();
  await expect(page.getByRole("button", { name: "What's the weather in Dallas this weekend?" })).toBeVisible();
  await expect(page.getByText(/Dallas is a guess from your network’s location/)).toBeVisible();
});

test.describe("the location pin", () => {
  test.use({ geolocation: { latitude: 48.85341, longitude: 2.3488 }, permissions: ["geolocation"] });

  test("puts your location, rounded to about 1 km, into the question", async ({ page }) => {
    await page.getByRole("button", { name: "Use my location" }).click();
    await expect(page.getByLabel("Your question")).toHaveValue("What's the weather at my location (48.85, 2.35)?");
    await expect(page.getByText(/rounded to about 1 km: 48.85, 2.35/)).toBeVisible();
  });
});

test("shows the same forecast call through the four lanes, side by side", async ({ page }) => {
  const hasToken = await hasApifyToken(page);
  await page.getByRole("button", { name: "Compare the four lanes" }).click();
  const cells = page.locator(".compare-cell");
  await expect(cells).toHaveCount(4);
  await expect(cells.nth(0).getByText(`GET ${FORECAST_URL}`)).toBeVisible();
  await expect(cells.nth(0)).toContainText("Live: ask in the chat on this lane");
  // REST · with auth: the Actor's run, the token masked; live where this deployment has the token, as the picker says.
  await expect(cells.nth(1).getByText(`POST ${ACTOR_RUN_URL}`)).toBeVisible();
  await expect(cells.nth(1).getByText("authorization: Bearer <APIFY_TOKEN>")).toBeVisible();
  await expect(cells.nth(1)).toContainText(
    hasToken ? "Live: ask in the chat on this lane" : "Built: it runs once this deployment has an Apify token",
  );
  await expect(cells.nth(2)).toContainText("Live: ask in the chat on this lane");
  await expect(cells.nth(2).getByText("mcp-method: tools/call")).toBeVisible();
  // MCP · with auth: a JSON-RPC tools/call to Apify's MCP server, the token and the session's id masked.
  await expect(
    cells.nth(3).getByText("POST https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast"),
  ).toBeVisible();
  await expect(cells.nth(3).getByText("authorization: Bearer <APIFY_TOKEN>")).toBeVisible();
  await expect(cells.nth(3)).toContainText(
    hasToken ? "Live: ask in the chat on this lane" : "Built: it runs once this deployment has an Apify token",
  );
});

test("has no accessibility violations, with an answer, an open chip and the compare view", async ({ page }) => {
  await answerWithParis(page);
  await askParis(page);
  await page.locator("details.tool-chip summary").first().click();
  await page.getByRole("button", { name: "Compare the four lanes" }).click();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("fits the screen without scrolling sideways, with an answer and the compare view", async ({ page }) => {
  await answerWithParis(page);
  await askParis(page);
  await page.locator("details.tool-chip summary").nth(1).click();
  await page.getByRole("button", { name: "Compare the four lanes" }).click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
