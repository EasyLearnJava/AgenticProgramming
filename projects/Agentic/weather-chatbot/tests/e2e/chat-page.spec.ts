/*
 * tests/e2e/chat-page.spec.ts: the chat page in a real browser: the sample conversation, the tool chips' wire views
 * for each lane, the keyboard, the compare view, accessibility (axe) and a 360-pixel screen.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("shows the sample conversation, with the menu and the build line", async ({ page }) => {
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Do I need an umbrella in Paris tomorrow afternoon?")).toBeVisible();
  await expect(page.getByText(/^No umbrella needed/)).toBeVisible();
  await expect(page.getByText(/^Build/)).toBeVisible();
});

test("opens a tool chip to show the request on the wire, and switches it with the lane", async ({ page }) => {
  // The forecast chip: its summary reads "… 2 days, hourly" on every lane.
  const forecastChip = page
    .locator("details.tool-chip")
    .filter({ has: page.locator("summary", { hasText: "2 days, hourly" }) });
  await expect(forecastChip).not.toHaveAttribute("open");
  await forecastChip.locator("summary").click();
  await expect(forecastChip).toHaveAttribute("open", "");
  await expect(forecastChip.getByText("POST https://<this deployment>/api/mcp")).toBeVisible();
  await expect(forecastChip.getByText('"method":"tools/call"')).toBeVisible();

  // The same chip, still open, now shows the call through Apify's REST API, with the token.
  await page.getByLabel(/REST · with auth/).check();
  await expect(forecastChip).toHaveAttribute("open", "");
  await expect(forecastChip.locator("summary")).toContainText("gochujang--open-meteo-weather-forecast");
  await expect(forecastChip.locator("summary")).toContainText("api.apify.com");
  await expect(forecastChip.getByText("Authorization: Bearer <APIFY_TOKEN>")).toBeVisible();
});

test("moves between the lanes with the arrow keys", async ({ page }) => {
  const mcpNoAuth = page.getByLabel(/MCP · no auth/);
  await expect(mcpNoAuth).toBeChecked();
  await mcpNoAuth.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByLabel(/MCP · with auth/)).toBeChecked();
});

test("shows the same call through the four lanes, side by side", async ({ page }) => {
  await page.getByRole("button", { name: "Compare the four lanes" }).click();
  const cells = page.locator(".compare-cell");
  await expect(cells).toHaveCount(4);
  await expect(cells.nth(0).getByText("GET https://api.open-meteo.com/v1/forecast")).toBeVisible();
  await expect(cells.nth(3).getByText("POST https://mcp.apify.com/")).toBeVisible();
});

test("has no accessibility violations, with a chip and the compare view open", async ({ page }) => {
  await page.locator("details.tool-chip summary").first().click();
  await page.getByRole("button", { name: "Compare the four lanes" }).click();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("fits the screen without scrolling sideways", async ({ page }) => {
  await page.getByRole("button", { name: "Compare the four lanes" }).click();
  await page.locator("details.tool-chip summary").first().click();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
