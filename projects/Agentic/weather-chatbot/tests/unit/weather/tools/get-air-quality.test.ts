/*
 * tests/unit/weather/tools/get-air-quality.test.ts: get_air_quality, on Open-Meteo's recorded answer for Delhi.
 */
import { describe, expect, it } from "vitest";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { getAirQuality } from "@/lib/weather/tools/get-air-quality";
import { createFakeFetch, createMemoryCache } from "@/tests/stubs/open-meteo-stand-ins";

describe("get_air_quality", () => {
  it("gives the air quality now in Delhi", async () => {
    const fake = createFakeFetch([{ fixture: "air-delhi" }]);
    const openMeteo = createOpenMeteoClient({ fetch: fake.fetch, cache: createMemoryCache() });
    const run = await getAirQuality.run({ latitude: 28.65195, longitude: 77.23149 }, { openMeteo });
    expect(fake.urls[0]).toBe(
      "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=28.65&longitude=77.23" +
        "&current=pm2_5,pm10,european_aqi,us_aqi&timezone=auto",
    );
    expect(run.output).toMatchObject({ timeZone: "Asia/Kolkata", pm25: 23.2, pm10: 25.8, europeanAqi: 45, usAqi: 131 });
    expect(getAirQuality.summarize(run.output)).toBe("US AQI 131 · European AQI 45");
  });
});
