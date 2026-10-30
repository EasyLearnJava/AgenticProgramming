/*
 * lib/weather/actor-items.ts: the Apify Actor's items as our Forecast, for both auth lanes (PLAN.md 7.6), in the units
 * asked for: the Actor has no units option, and answers in Open-Meteo's own metric units.
 *
 * The Actor's output isn't documented. Its README says each record is one location, with "time-series arrays for
 * daily and hourly forecasts"; its dataset's overview lists name, latitude, longitude, timezone and forecast_days. So
 * this reads those, with Open-Meteo's own names inside the arrays, since the Actor calls Open-Meteo. A run on the live
 * site, once the token is set, checks it (step 6); until then, an item in any other shape is a ContractError, and the
 * lane falls back to REST · no auth instead of guessing.
 */
import "server-only";
import { z } from "zod";
import { MAX_HOURLY_DAYS } from "@/lib/constants";
import { ContractError } from "@/lib/errors";
import type { Forecast, ForecastDay, ForecastHour, Units } from "@/lib/types";
import { celsiusToFahrenheit, roundCoordinate, toWeekday } from "@/lib/utils";
import { toCondition } from "@/lib/weather/wmo-codes";

const HOURS_PER_DAY = 24;
const CELSIUS = "°C";
const FAHRENHEIT = "°F";

const numbers = z.array(z.number().nullable());
const times = z.array(z.string());

// ① One item, as we expect the Actor to give it: a location, and Open-Meteo's daily and hourly arrays.
const ActorItemSchema = z
  .object({
    name: z.string(),
    latitude: z.number(),
    longitude: z.number(),
    timezone: z.string(),
    daily_units: z.object({ temperature_2m_max: z.string() }).optional(),
    daily: z
      .object({
        time: times,
        weather_code: numbers,
        temperature_2m_max: numbers,
        temperature_2m_min: numbers,
        precipitation_probability_max: numbers.optional(),
        sunrise: z.array(z.string().nullable()).optional(),
        sunset: z.array(z.string().nullable()).optional(),
      })
      .optional(),
    hourly: z
      .object({
        time: times,
        temperature_2m: numbers,
        precipitation_probability: numbers.optional(),
        weather_code: numbers,
      })
      .optional(),
  })
  .refine((item) => item.daily !== undefined || item.hourly !== undefined, { message: "no daily or hourly data" });

type ActorItem = z.output<typeof ActorItemSchema>;

/** A temperature in the units asked for: Open-Meteo's °C as it is, or in °F. */
function toTemperature(celsius: number | null, units: Units): number | null {
  return celsius === null || units === "metric" ? celsius : celsiusToFahrenheit(celsius);
}

/** The item's days, in the units asked for; none, when the Actor gave only hours. */
function toDays(daily: ActorItem["daily"], units: Units): ForecastDay[] {
  if (daily === undefined) {
    return [];
  }
  return daily.time.map((date, i) => {
    const condition = toCondition(daily.weather_code[i] ?? null);
    return {
      date,
      weekday: toWeekday(date),
      condition: condition.words,
      icon: condition.icon,
      temperatureMin: toTemperature(daily.temperature_2m_min[i] ?? null, units),
      temperatureMax: toTemperature(daily.temperature_2m_max[i] ?? null, units),
      rainChancePercent: daily.precipitation_probability_max?.[i] ?? null,
      sunrise: daily.sunrise?.[i] ?? null,
      sunset: daily.sunset?.[i] ?? null,
    };
  });
}

/** The item's hours, if it has them, for the first 3 days at most, as get_forecast gives them. */
function toHours(hourly: ActorItem["hourly"], units: Units): ForecastHour[] | undefined {
  return hourly?.time.slice(0, MAX_HOURLY_DAYS * HOURS_PER_DAY).map((time, i) => ({
    time,
    temperature: toTemperature(hourly.temperature_2m[i] ?? null, units),
    rainChancePercent: hourly.precipitation_probability?.[i] ?? null,
    condition: toCondition(hourly.weather_code[i] ?? null).words,
  }));
}

/**
 * The Actor's answer for one location as our Forecast, in the units asked for. Anything else (more or fewer items, a
 * missing field, units other than °C) is a ContractError that names what's wrong, never a value.
 */
export function toForecast(
  items: readonly unknown[],
  { units, fetchedAt }: { units: Units; fetchedAt: string },
): Forecast {
  // ② One location went in, so one item comes back, in the shape above.
  if (items.length !== 1) {
    throw new ContractError(`The Actor gave ${items.length} items for one location.`);
  }
  const parsed = ActorItemSchema.safeParse(items[0]);
  if (!parsed.success) {
    // A field's name, without the array index where a value broke it: "daily.time", not "daily.time.3".
    const fields = parsed.error.issues.map(
      (issue) => issue.path.filter((key) => typeof key !== "number").join(".") || issue.message,
    );
    throw new ContractError(`The Actor's item isn't the shape we read: ${[...new Set(fields)].join(", ")}.`);
  }
  const item = parsed.data;
  // ③ The Actor answers in °C, Open-Meteo's default; another unit is a contract problem, not something to guess at.
  const sourceUnit = item.daily_units?.temperature_2m_max ?? CELSIUS;
  if (sourceUnit !== CELSIUS) {
    throw new ContractError(`The Actor's temperature unit isn't ${CELSIUS}.`);
  }
  // ④ Our Forecast: rounded coordinates, the place's time zone, and the days and hours in the units asked for.
  return {
    latitude: roundCoordinate(item.latitude),
    longitude: roundCoordinate(item.longitude),
    timeZone: item.timezone,
    temperatureUnit: units === "imperial" ? FAHRENHEIT : CELSIUS,
    days: toDays(item.daily, units),
    hours: toHours(item.hourly, units),
    fetchedAt,
  };
}
