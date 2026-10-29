/*
 * tests/e2e/docs.spec.ts: the documentation in a real browser: the list of steps, a step's page, the 404 page, and
 * accessibility (axe).
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("lists the steps, and opens one from the menu", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Documentation" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Documentation" })).toBeVisible();
  await page.getByRole("link", { name: /^Step 3:/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: /^Step 3 · / })).toBeVisible();
  await expect(page.getByRole("link", { name: "Documentation" })).toHaveAttribute("aria-current", "true");
});

test("follows a link written for GitHub (step-3.md) to that step's page in the app", async ({ page }) => {
  await page.goto("/docs/step-2");
  await page.getByRole("link", { name: "step 3", exact: true }).click();
  await expect(page).toHaveURL(/\/docs\/step-3$/);
  await expect(page.getByRole("heading", { level: 1, name: /^Step 3 · / })).toBeVisible();
});

test("opens Issues and fixes from the menu: a section for each step", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Issues and fixes" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Issues and Fixes" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Issues and fixes" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { level: 2, name: /^Step 3 · / })).toBeVisible();
});

test("answers an unknown address with the app's own 404 page", async ({ page }) => {
  const response = await page.goto("/docs/step-unknown");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
});

test("has no accessibility violations on a documentation page, or on the issues log", async ({ page }) => {
  for (const address of ["/docs/step-5", "/issues"]) {
    await page.goto(address);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations, address).toEqual([]);
  }
});

test("fits a documentation page, tables included, on the screen without scrolling sideways", async ({ page }) => {
  for (const address of ["/docs/step-1", "/docs/step-2", "/docs/step-3", "/docs/step-4", "/docs/step-5", "/issues"]) {
    await page.goto(address);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, address).toBeLessThanOrEqual(0);
  }
});
