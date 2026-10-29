/*
 * tests/unit/docs/doc-list.test.ts: the documentation's list holds each step once, in order, and finds pages by slug.
 */
import { describe, expect, it } from "vitest";
import { DOC_PAGES, findDoc } from "@/lib/docs/doc-list";

describe("DOC_PAGES", () => {
  it("lists the steps in order, each slug once", () => {
    const steps = DOC_PAGES.map((doc) => doc.step);
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
    expect(new Set(DOC_PAGES.map((doc) => doc.slug)).size).toBe(DOC_PAGES.length);
  });
});

describe("findDoc", () => {
  it("finds a page by its slug, and nothing for an unknown slug", () => {
    expect(findDoc("step-1")?.step).toBe(1);
    expect(findDoc("step-unknown")).toBeUndefined();
  });
});
