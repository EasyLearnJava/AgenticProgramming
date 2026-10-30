/*
 * tests/unit/weather/tools/open-meteo-actor.test.ts: the auth lanes' Actor tool: the input it takes (one place; hourly
 * mode for at most 3 days), and the chip's one-line summary, for days and, from hourly mode, for hours.
 */
import { describe, expect, it } from "vitest";
import type { Forecast } from "@/lib/types";
import { openMeteoActor } from "@/lib/weather/tools/open-meteo-actor";

const DALLAS = { name: "Dallas", latitude: 32.78, longitude: -96.81 };

/** Whether the tool's input schema takes this input. */
function takes(input: unknown): boolean {
  return openMeteoActor.inputSchema.safeParse(input).success;
}

describe("the Actor tool's input", () => {
  it("takes one place, 1 to 16 days daily, and 1 to 3 days hourly", () => {
    expect(takes({ locations: [DALLAS], forecastDays: 16, mode: "daily", units: "metric" })).toBe(true);
    expect(takes({ locations: [DALLAS], forecastDays: 3, mode: "hourly", units: "imperial" })).toBe(true);
    expect(takes({ locations: [DALLAS], forecastDays: 4, mode: "hourly", units: "metric" })).toBe(false);
    expect(takes({ locations: [DALLAS], forecastDays: 17, mode: "daily", units: "metric" })).toBe(false);
    expect(takes({ locations: [DALLAS, DALLAS], forecastDays: 1, mode: "daily", units: "metric" })).toBe(false);
  });
});

describe("the Actor tool's summary", () => {
  const base: Forecast = {
    latitude: 32.78,
    longitude: -96.81,
    timeZone: "America/Chicago",
    localNow: "2026-10-29T11:00",
    temperatureUnit: "°C",
    days: [],
    fetchedAt: "2026-10-29T16:00:00.000Z",
  };

  it("sums up days as get_forecast does", () => {
    const day = { weekday: "Thursday", condition: "Overcast", icon: "☁️", sunrise: null, sunset: null };
    const days = [
      { ...day, date: "2026-10-29", temperatureMin: 19.8, temperatureMax: 26.6, rainChancePercent: 17 },
      { ...day, date: "2026-10-30", temperatureMin: 19.6, temperatureMax: 24.5, rainChancePercent: 13 },
    ];
    expect(openMeteoActor.summarize({ ...base, days })).toBe("2 days · 20 to 27 °C · rain up to 17%");
  });

  it("sums up hours, when hourly mode gave no days", () => {
    const hours = [
      { time: "2026-10-29T06:00", temperature: 19.8, rainChancePercent: 0, condition: "Partly cloudy" },
      { time: "2026-10-29T13:00", temperature: 26.6, rainChancePercent: 2, condition: "Overcast" },
      { time: "2026-10-29T20:00", temperature: 20.6, rainChancePercent: 17, condition: "Overcast" },
    ];
    expect(openMeteoActor.summarize({ ...base, hours })).toBe("3 hours · 20 to 27 °C · rain up to 17%");
  });
});
