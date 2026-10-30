/*
 * lib/weather/actor-items.ts: the Apify Actor's items as our Forecast, for both auth lanes (PLAN.md 7.6), in the units
 * asked for: the Actor has no units option, and answers in °C, as its field names say (temp_max_c, temperature_c).
 *
 * The Actor's output isn't documented. Its first runs on the live site showed it (29 October 2026, build 1.0.9): one
 * item per day in daily mode, and one per hour in hourly mode, each carrying its place, with the coordinates it was
 * sent. tests/fixtures/apify/ holds those answers. Anything else (another shape, another place, a day missing) is a
 * ContractError that names the field, never its value, and the lane falls back instead of guessing.
 */
import "server-only";
import { z } from "zod";
import { ContractError } from "@/lib/errors";
import type { Forecast, ForecastDay, ForecastHour, Units } from "@/lib/types";
import { addDays, celsiusToFahrenheit, roundCoordinate, toFieldNames, toLocalDateTime, toWeekday } from "@/lib/utils";
import { toCondition } from "@/lib/weather/wmo-codes";

const CELSIUS = "°C";
const FAHRENHEIT = "°F";
// A day as the Actor writes it, "2026-10-29", and an hour, "2026-10-29T13:00": both in the place's own time.
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const HOUR_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const DATE_CHARS = 10;
// The Actor echoes the coordinates it was sent, rounded to 2 decimals, as the lane sends them: this close is the same.
const SAME_PLACE_DEGREES = 0.01;

const reading = z.number().nullable();

// ① What every item carries: the place, as the Actor read it.
const PLACE_FIELDS = {
  location: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  timezone: z.string(),
};

// ② An item in daily mode: one day. The fields we use; zod drops the rest (precipitation, wind, UV).
const DailyItemSchema = z.object({
  ...PLACE_FIELDS,
  date: z.string().regex(DATE_PATTERN),
  weather_code: reading,
  temp_max_c: reading,
  temp_min_c: reading,
  precipitation_probability_pct: reading,
  sunrise: z.string().nullable(),
  sunset: z.string().nullable(),
});

// ③ An item in hourly mode: one hour. The fields we use; zod drops the rest (feels-like, humidity, wind).
const HourlyItemSchema = z.object({
  ...PLACE_FIELDS,
  datetime: z.string().regex(HOUR_PATTERN),
  weather_code: reading,
  temperature_c: reading,
  precipitation_probability_pct: reading,
});

type DailyItem = z.output<typeof DailyItemSchema>;
type HourlyItem = z.output<typeof HourlyItemSchema>;
type Place = Pick<DailyItem, "location" | "latitude" | "longitude" | "timezone">;

/**
 * What the lane asked the Actor for, and what to give back: the place's coordinates as sent, the mode and days, the
 * units, and when the answer came.
 */
export type ActorAsk = {
  place: { latitude: number; longitude: number };
  mode: "daily" | "hourly";
  forecastDays: number;
  units: Units;
  fetchedAt: string;
};

/** A temperature in the units asked for: the Actor's °C as it is, or in °F. */
function toTemperature(celsius: number | null, units: Units): number | null {
  return celsius === null || units === "metric" ? celsius : celsiusToFahrenheit(celsius);
}

/** The items in the shape their mode gives, or a ContractError naming the fields that aren't, never their values. */
function parseItems<Item>(items: readonly unknown[], schema: z.ZodType<Item>, mode: ActorAsk["mode"]): Item[] {
  if (items.length === 0) {
    throw new ContractError("The Actor gave no items.");
  }
  const parsed = z.array(schema).safeParse(items);
  if (!parsed.success) {
    throw new ContractError(
      `The Actor's ${mode} items aren't the shape we read: ${toFieldNames(parsed.error.issues)}.`,
    );
  }
  return parsed.data;
}

/**
 * The place every item is for: the one asked, at the coordinates the lane sent, and the same name and time zone in
 * each. An item for any other is a ContractError.
 */
function toPlace(items: readonly Place[], { place }: ActorAsk): Place {
  const [first] = items;
  const isPlaceAsked = (item: Place) =>
    Math.abs(item.latitude - place.latitude) <= SAME_PLACE_DEGREES &&
    Math.abs(item.longitude - place.longitude) <= SAME_PLACE_DEGREES &&
    item.location === first?.location &&
    item.timezone === first.timezone;
  if (first === undefined || !items.every(isPlaceAsked)) {
    throw new ContractError("The Actor's items aren't all for the one place asked.");
  }
  return first;
}

/**
 * Checks that the items cover as many days as asked, one after another: one item a day in daily mode, the days'
 * hours in hourly mode.
 */
function checkDays(dates: readonly string[], { mode, forecastDays }: ActorAsk): void {
  const days = [...new Set(dates)];
  if (days.length !== forecastDays) {
    const gave = `${days.length} ${days.length === 1 ? "day" : "days"}`;
    throw new ContractError(`The Actor gave ${gave} for the ${forecastDays} asked.`);
  }
  if (mode === "daily" && dates.length !== days.length) {
    throw new ContractError("The Actor gave a day twice.");
  }
  if (days.some((date, i) => i > 0 && date !== addDays(days[i - 1] ?? date, 1))) {
    throw new ContractError("The Actor's days don't follow one another.");
  }
}

/** A daily item as our day, in the units asked for. */
function toDay(item: DailyItem, units: Units): ForecastDay {
  const condition = toCondition(item.weather_code);
  return {
    date: item.date,
    weekday: toWeekday(item.date),
    condition: condition.words,
    icon: condition.icon,
    temperatureMin: toTemperature(item.temp_min_c, units),
    temperatureMax: toTemperature(item.temp_max_c, units),
    rainChancePercent: item.precipitation_probability_pct,
    sunrise: item.sunrise,
    sunset: item.sunset,
  };
}

/** An hourly item as our hour, in the units asked for. */
function toHour(item: HourlyItem, units: Units): ForecastHour {
  return {
    time: item.datetime,
    temperature: toTemperature(item.temperature_c, units),
    rainChancePercent: item.precipitation_probability_pct,
    condition: toCondition(item.weather_code).words,
  };
}

/**
 * The Actor's answer for one place as our Forecast, in the units asked for: its days in daily mode; its hours, and no
 * days, in hourly mode, since that mode gives no day's summary. Anything else is a ContractError.
 */
export function toForecast(items: readonly unknown[], ask: ActorAsk): Forecast {
  const temperatureUnit = ask.units === "imperial" ? FAHRENHEIT : CELSIUS;
  const toForecastOf = (place: Place, days: ForecastDay[], hours: ForecastHour[] | undefined): Forecast => ({
    latitude: roundCoordinate(place.latitude),
    longitude: roundCoordinate(place.longitude),
    timeZone: place.timezone,
    localNow: toLocalDateTime(ask.fetchedAt, place.timezone),
    temperatureUnit,
    days,
    hours,
    fetchedAt: ask.fetchedAt,
  });
  if (ask.mode === "daily") {
    const daily = parseItems(items, DailyItemSchema, ask.mode);
    const place = toPlace(daily, ask);
    checkDays(
      daily.map((item) => item.date),
      ask,
    );
    return toForecastOf(
      place,
      daily.map((item) => toDay(item, ask.units)),
      undefined,
    );
  }
  const hourly = parseItems(items, HourlyItemSchema, ask.mode);
  const place = toPlace(hourly, ask);
  checkDays(
    hourly.map((item) => item.datetime.slice(0, DATE_CHARS)),
    ask,
  );
  return toForecastOf(
    place,
    [],
    hourly.map((item) => toHour(item, ask.units)),
  );
}
