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
  await page.getByRole("link", { name: /^Step 2:/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: /^Step 2 · / })).toBeVisible();
  await expect(page.getByRole("link", { name: "Documentation" })).toHaveAttribute("aria-current", "true");
});

test("answers an unknown address with the app's own 404 page", async ({ page }) => {
  const response = await page.goto("/docs/step-unknown");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
});

test("has no accessibility violations on a documentation page", async ({ page }) => {
  await page.goto("/docs/step-2");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("fits a documentation page, tables included, on the screen without scrolling sideways", async ({ page }) => {
  for (const address of ["/docs/step-1", "/docs/step-2"]) {
    await page.goto(address);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, address).toBeLessThanOrEqual(0);
  }
});
