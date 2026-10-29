/*
 * tests/unit/weather/ambiguity.test.ts: the ambiguity rule, on the places Open-Meteo really returned (29 October 2026).
 */
import { describe, expect, it } from "vitest";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { isAmbiguousPlace } from "@/lib/weather/ambiguity";
import { createFakeFetch, createMemoryCache } from "@/tests/stubs/open-meteo-stand-ins";

/** The places Open-Meteo returned for a name, from its recorded answer. */
async function placesFrom(fixture: string) {
  const client = createOpenMeteoClient({ fetch: createFakeFetch([{ fixture }]).fetch, cache: createMemoryCache() });
  return (await client.searchPlaces({ query: fixture, count: 5 })).data;
}

describe("isAmbiguousPlace", () => {
  it("isn't ambiguous for Paris: the next largest, in Texas, has about 1% of its people", async () => {
    expect(isAmbiguousPlace(await placesFrom("geocode-paris"))).toBe(false);
  });

  it("is ambiguous for Springfield: Massachusetts has 154,341 people to Missouri's 170,188", async () => {
    expect(isAmbiguousPlace(await placesFrom("geocode-springfield"))).toBe(true);
  });

  it("isn't ambiguous for Springfield, MA: every place found is in Massachusetts", async () => {
    expect(isAmbiguousPlace(await placesFrom("geocode-springfield-ma"))).toBe(false);
  });

  it("is ambiguous when the largest place's population is unknown, as for Narnia", async () => {
    expect(isAmbiguousPlace(await placesFrom("geocode-narnia"))).toBe(true);
  });

  it("isn't ambiguous for Atlantis, a real town in South Africa, nor for a name with no place", async () => {
    expect(isAmbiguousPlace(await placesFrom("geocode-atlantis"))).toBe(false);
    expect(isAmbiguousPlace(await placesFrom("geocode-hogwarts"))).toBe(false);
  });

  it("isn't ambiguous for a single place", () => {
    expect(isAmbiguousPlace([{ name: "Lyon", countryCode: "FR", latitude: 45.75, longitude: 4.85 }])).toBe(false);
  });
});
