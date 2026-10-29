/*
 * tests/unit/weather/tools/get-current-weather.test.ts: get_current_weather, on Open-Meteo's recorded answer for Tokyo.
 */
import { describe, expect, it } from "vitest";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { getCurrentWeather } from "@/lib/weather/tools/get-current-weather";
import { createFakeFetch, createMemoryCache } from "@/tests/stubs/open-meteo-stand-ins";

describe("get_current_weather", () => {
  it("gives the weather now in Tokyo, in WMO's words and Tokyo time", async () => {
    const openMeteo = createOpenMeteoClient({
      fetch: createFakeFetch([{ fixture: "current-tokyo" }]).fetch,
      cache: createMemoryCache(),
    });
    const run = await getCurrentWeather.run(
      { latitude: 35.6895, longitude: 139.69171, units: "metric" },
      { openMeteo },
    );
    expect(run.output).toMatchObject({
      latitude: 35.69,
      longitude: 139.69,
      timeZone: "Asia/Tokyo",
      observedAt: "2026-10-30T04:00",
      temperature: 12,
      feelsLike: 11.3,
      windSpeed: 2.2,
      condition: "Partly cloudy",
      isDay: false,
      temperatureUnit: "°C",
      windSpeedUnit: "km/h",
    });
    expect(getCurrentWeather.summarize(run.output)).toBe("12 °C, partly cloudy");
  });
});
