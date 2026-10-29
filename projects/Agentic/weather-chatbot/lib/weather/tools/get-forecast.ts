/*
 * lib/weather/tools/get-forecast.ts: get_forecast gives a point's forecast, per day and, if asked, per hour, in the
 * place's local time, from Open-Meteo's forecast API.
 */
import "server-only";
import { z } from "zod";
import { MAX_FORECAST_DAYS, MAX_HOURLY_DAYS } from "@/lib/constants";
import type { Forecast, ForecastInput } from "@/lib/types";
import { roundCoordinate, toWeekday } from "@/lib/utils";
import { LatitudeSchema, LongitudeSchema, type WeatherTool } from "@/lib/weather/weather-tool";
import { toCondition } from "@/lib/weather/wmo-codes";

const ForecastInputSchema: z.ZodType<ForecastInput> = z.object({
  latitude: LatitudeSchema,
  longitude: LongitudeSchema,
  days: z
    .number()
    .int()
    .min(1)
    .max(MAX_FORECAST_DAYS)
    .describe(`How many days, counting today in that place: 1 to ${MAX_FORECAST_DAYS}.`),
  includeHourly: z
    .boolean()
    .describe(`Also give each hour of the first ${MAX_HOURLY_DAYS} days: for a part of a day, such as an afternoon.`),
  units: z.enum(["metric", "imperial"]).describe("metric: °C, km/h, mm. imperial: °F, mph, inches."),
});

export const getForecast: WeatherTool<"get_forecast", ForecastInput, Forecast> = {
  name: "get_forecast",
  description:
    "Gives the forecast for a point, per day (condition, lowest and highest temperature, the highest chance of " +
    "rain, sunrise, sunset) and, if asked, per hour. The first day is today in that place; times are local.",
  inputSchema: ForecastInputSchema,
  async run(input, { openMeteo, signal, log }) {
    const answer = await openMeteo.getForecast(input, { signal, log });
    const { data } = answer;
    const output: Forecast = {
      latitude: roundCoordinate(input.latitude),
      longitude: roundCoordinate(input.longitude),
      timeZone: data.timeZone,
      temperatureUnit: data.temperatureUnit,
      days: data.days.map(({ weatherCode, ...day }) => ({
        ...day,
        weekday: toWeekday(day.date),
        condition: toCondition(weatherCode).words,
        icon: toCondition(weatherCode).icon,
      })),
      hours: data.hours?.map(({ weatherCode, ...hour }) => ({ ...hour, condition: toCondition(weatherCode).words })),
      fetchedAt: answer.fetchedAt,
    };
    return { output, request: answer.request, cache: answer.cache };
  },
  summarize({ days, hours, temperatureUnit }) {
    const lows = days.map((day) => day.temperatureMin).filter((value) => value !== null);
    const highs = days.map((day) => day.temperatureMax).filter((value) => value !== null);
    const rain = days.map((day) => day.rainChancePercent).filter((value) => value !== null);
    const range =
      lows.length > 0 ? `${Math.round(Math.min(...lows))} to ${Math.round(Math.max(...highs))} ${temperatureUnit}` : "";
    const rainPart = rain.length > 0 ? `rain up to ${Math.max(...rain)}%` : "";
    const span = `${days.length} ${days.length === 1 ? "day" : "days"}${hours ? ", hourly" : ""}`;
    return [span, range, rainPart].filter(Boolean).join(" · ");
  },
};
