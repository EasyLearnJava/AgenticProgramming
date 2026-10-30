/*
 * tests/unit/weather/actor-items.test.ts: the Actor's items as our Forecast, against its real answers for Dallas
 * (tests/fixtures/apify/, from the live check on 29 October 2026): its days in daily mode, its hours (and no days) in
 * hourly mode, °F when asked; and a ContractError for any other answer, naming the field and never its value.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ContractError } from "@/lib/errors";
import { type ActorAsk, toForecast } from "@/lib/weather/actor-items";

const FETCHED_AT = "2026-10-29T16:00:00.000Z";
// The place the lane sent, which the Actor echoes in each item.
const DALLAS = { latitude: 32.78, longitude: -96.81 };
const DAILY_ASK: ActorAsk = { place: DALLAS, mode: "daily", forecastDays: 3, units: "metric", fetchedAt: FETCHED_AT };
const HOURLY_ASK: ActorAsk = { place: DALLAS, mode: "hourly", forecastDays: 1, units: "metric", fetchedAt: FETCHED_AT };

/** One of the Actor's real answers, from tests/fixtures/apify/. */
function readItems(name: string): Record<string, unknown>[] {
  return JSON.parse(
    readFileSync(path.join(import.meta.dirname, "..", "..", "fixtures", "apify", `${name}.json`), "utf8"),
  );
}

const DAILY = readItems("actor-dallas-daily");
const HOURLY = readItems("actor-dallas-hourly");

/** The ContractError's message that reading these items gives, or "no error". */
function refusal(items: unknown[], ask: ActorAsk): string {
  try {
    toForecast(items, ask);
  } catch (error) {
    expect(error).toBeInstanceOf(ContractError);
    return (error as Error).message;
  }
  return "no error";
}

describe("toForecast, daily", () => {
  it("gives a day per item: its weekday, our words for its code, its temperatures, rain, sunrise and sunset", () => {
    const forecast = toForecast(DAILY, DAILY_ASK);
    expect(forecast).toMatchObject({ latitude: 32.78, longitude: -96.81, timeZone: "America/Chicago" });
    expect(forecast).toMatchObject({ temperatureUnit: "°C", hours: undefined, fetchedAt: FETCHED_AT });
    expect(forecast.days).toEqual([
      {
        date: "2026-10-29",
        weekday: "Thursday",
        condition: "Overcast",
        icon: "☁️",
        temperatureMin: 19.8,
        temperatureMax: 26.6,
        rainChancePercent: 17,
        sunrise: "2026-10-29T07:42",
        sunset: "2026-10-29T18:38",
      },
      expect.objectContaining({ date: "2026-10-30", condition: "Light drizzle", rainChancePercent: 13 }),
      expect.objectContaining({ date: "2026-10-31", temperatureMin: 16.7, temperatureMax: 24, rainChancePercent: 45 }),
    ]);
  });

  it("gives °F when asked, from the Actor's °C, to a tenth of a degree", () => {
    const forecast = toForecast(DAILY, { ...DAILY_ASK, units: "imperial" });
    expect(forecast.temperatureUnit).toBe("°F");
    expect(forecast.days.map((day) => [day.temperatureMin, day.temperatureMax])).toEqual([
      [67.6, 79.9],
      [67.3, 76.1],
      [62.1, 75.2],
    ]);
  });
});

describe("toForecast, hourly", () => {
  it("gives an hour per item, from the place's midnight, and no days: hourly mode gives no day's summary", () => {
    const forecast = toForecast(HOURLY, HOURLY_ASK);
    expect(forecast.days).toEqual([]);
    expect(forecast.hours).toHaveLength(24);
    expect(forecast.hours?.[0]).toEqual({
      time: "2026-10-29T00:00",
      temperature: 22.2,
      rainChancePercent: 0,
      condition: "Clear sky",
    });
    expect(forecast.hours?.[20]).toEqual({
      time: "2026-10-29T20:00",
      temperature: 20.6,
      rainChancePercent: 17,
      condition: "Overcast",
    });
    expect(toForecast(HOURLY, { ...HOURLY_ASK, units: "imperial" }).hours?.[0]?.temperature).toBe(72);
  });
});

describe("toForecast, refusing", () => {
  it("refuses an answer in the other mode's shape, naming the fields it lacks", () => {
    expect(refusal(HOURLY, { ...DAILY_ASK, forecastDays: 1 })).toBe(
      "The Actor's daily items aren't the shape we read: date, temp_max_c, temp_min_c, sunrise, sunset.",
    );
    expect(refusal(DAILY, { ...HOURLY_ASK, forecastDays: 3 })).toBe(
      "The Actor's hourly items aren't the shape we read: datetime, temperature_c.",
    );
  });

  it("names a field whose value is wrong, never the value, nor which item it was in", () => {
    const wrong = DAILY.map((item, i) => (i === 2 ? { ...item, temp_max_c: "twenty-four" } : item));
    expect(refusal(wrong, DAILY_ASK)).toBe("The Actor's daily items aren't the shape we read: temp_max_c.");
  });

  it("refuses no items, an answer for another place, even all of it, and a missing, doubled or skipped day", () => {
    expect(refusal([], DAILY_ASK)).toBe("The Actor gave no items.");
    const oneElsewhere = DAILY.map((item, i) => (i === 1 ? { ...item, location: "Austin", latitude: 30.27 } : item));
    expect(refusal(oneElsewhere, DAILY_ASK)).toBe("The Actor's items aren't all for the one place asked.");
    const allElsewhere = DAILY.map((item) => ({ ...item, location: "Austin", latitude: 30.27, longitude: -97.74 }));
    expect(refusal(allElsewhere, DAILY_ASK)).toBe("The Actor's items aren't all for the one place asked.");
    expect(refusal([DAILY[0], DAILY[2]], { ...DAILY_ASK, forecastDays: 2 })).toBe(
      "The Actor's days don't follow one another.",
    );
    expect(refusal(DAILY.slice(0, 2), DAILY_ASK)).toBe("The Actor gave 2 days for the 3 asked.");
    expect(refusal([DAILY[0], DAILY[0], DAILY[1]], { ...DAILY_ASK, forecastDays: 2 })).toBe(
      "The Actor gave a day twice.",
    );
    expect(refusal(HOURLY, { ...HOURLY_ASK, forecastDays: 2 })).toBe("The Actor gave 1 day for the 2 asked.");
  });
});
