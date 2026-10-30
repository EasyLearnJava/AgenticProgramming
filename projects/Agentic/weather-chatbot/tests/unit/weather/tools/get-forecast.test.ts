/*
 * tests/unit/weather/tools/get-forecast.test.ts: get_forecast, on Open-Meteo's recorded answers for Paris and Dallas.
 */
import { describe, expect, it } from "vitest";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { getForecast } from "@/lib/weather/tools/get-forecast";
import { createFakeFetch, createMemoryCache } from "@/tests/stubs/open-meteo-stand-ins";

const NOW = new Date("2026-10-29T16:00:00Z");

/** Runs the tool once, with Open-Meteo's recorded answer. */
async function runWith(fixture: string, input: Parameters<typeof getForecast.run>[0]) {
  const fake = createFakeFetch([{ fixture }]);
  const openMeteo = createOpenMeteoClient({ fetch: fake.fetch, cache: createMemoryCache(), now: () => NOW });
  return getForecast.run(input, { openMeteo });
}

describe("get_forecast", () => {
  it("gives each day's weekday and WMO words, and each hour's, in Paris time", async () => {
    const run = await runWith("forecast-paris", {
      latitude: 48.85341,
      longitude: 2.3488,
      days: 2,
      includeHourly: true,
      units: "metric",
    });
    expect(run.output).toMatchObject({
      latitude: 48.85,
      longitude: 2.35,
      timeZone: "Europe/Paris",
      localNow: "2026-10-29T17:00",
      fetchedAt: NOW.toISOString(),
    });
    expect(run.output.days[1]).toEqual({
      date: "2026-10-30",
      weekday: "Friday",
      condition: "Mainly clear",
      icon: "🌤️",
      temperatureMin: 6.1,
      temperatureMax: 15.3,
      rainChancePercent: 0,
      sunrise: "2026-10-30T07:34",
      sunset: "2026-10-30T17:33",
    });
    expect(run.output.hours?.[36]).toEqual({
      time: "2026-10-30T12:00",
      temperature: 12.1,
      rainChancePercent: 0,
      condition: "Clear sky",
    });
    expect(getForecast.summarize(run.output)).toBe("2 days, hourly · 6 to 16 °C · rain up to 0%");
  });

  it("gives Dallas in Fahrenheit, without hours", async () => {
    const run = await runWith("forecast-dallas-imperial", {
      latitude: 32.78,
      longitude: -96.8,
      days: 2,
      includeHourly: false,
      units: "imperial",
    });
    expect(run.output.temperatureUnit).toBe("°F");
    expect(run.output.hours).toBeUndefined();
    expect(run.request.url).toContain("temperature_unit=fahrenheit");
    expect(getForecast.summarize(run.output)).toBe("2 days · 65 to 80 °F · rain up to 23%");
  });

  it("refuses more than 16 days, and a latitude past the pole", () => {
    const valid = { latitude: 1, longitude: 1, days: 16, includeHourly: false, units: "metric" };
    expect(getForecast.inputSchema.safeParse(valid).success).toBe(true);
    expect(getForecast.inputSchema.safeParse({ ...valid, days: 17 }).success).toBe(false);
    expect(getForecast.inputSchema.safeParse({ ...valid, latitude: 91 }).success).toBe(false);
  });
});
