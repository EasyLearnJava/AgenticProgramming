/*
 * tests/unit/weather/tools/geocode-location.test.ts: geocode_location, on Open-Meteo's recorded answers.
 */
import { describe, expect, it } from "vitest";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { geocodeLocation } from "@/lib/weather/tools/geocode-location";
import { createFakeFetch, createMemoryCache } from "@/tests/stubs/open-meteo-stand-ins";

/** Runs the tool once, with Open-Meteo's recorded answer. */
async function runWith(fixture: string, query: string) {
  const fake = createFakeFetch([{ fixture }]);
  const openMeteo = createOpenMeteoClient({ fetch: fake.fetch, cache: createMemoryCache() });
  return { run: await geocodeLocation.run({ query }, { openMeteo }), urls: fake.urls };
}

describe("geocode_location", () => {
  it("asks for 5 places when the model doesn't say, and returns them with the ambiguity flag", async () => {
    const { run, urls } = await runWith("geocode-paris", "Paris");
    expect(urls[0]).toContain("name=Paris&count=5&");
    expect(run.output.candidates).toHaveLength(5);
    expect(run.output.isAmbiguous).toBe(false);
    expect(run.request.url).toBe(urls[0]);
    expect(geocodeLocation.summarize(run.output)).toBe("Paris, Île-de-France Region, FR · 48.85, 2.35");
  });

  it("sums up an ambiguous name, and a name no place has", async () => {
    expect(geocodeLocation.summarize((await runWith("geocode-springfield", "Springfield")).run.output)).toBe(
      "5 places, ambiguous",
    );
    expect(geocodeLocation.summarize((await runWith("geocode-hogwarts", "Hogwarts")).run.output)).toBe(
      "No place found",
    );
  });

  it("refuses an empty query and a count over 10", () => {
    expect(geocodeLocation.inputSchema.safeParse({ query: " " }).success).toBe(false);
    expect(geocodeLocation.inputSchema.safeParse({ query: "Paris", count: 11 }).success).toBe(false);
    expect(geocodeLocation.inputSchema.safeParse({ query: "Paris", countryCode: "USA" }).success).toBe(false);
  });
});
