/*
 * lib/weather/tools/open-meteo-actor.ts: the auth lanes' forecast tool, under the Apify Actor's own name
 * (gochujang--open-meteo-weather-forecast) and with its input: one location, 1 to 16 days, daily or hourly (PLAN.md
 * 7.6). Our units field is the one addition: the Actor has no such option, so the lane applies it and never sends it.
 * It runs the Actor through lib/upstream/apify.ts, and reads its items with lib/weather/actor-items.ts.
 */
import "server-only";
import { z } from "zod";
import { ACTOR_TOOL_NAME, MAX_FORECAST_DAYS, MAX_HOURLY_DAYS, MAX_QUERY_CHARS } from "@/lib/constants";
import type { Logger } from "@/lib/logger";
import type { ActorForecastInput, Forecast } from "@/lib/types";
import type { ApifyClient } from "@/lib/upstream/apify";
import { roundCoordinate } from "@/lib/utils";
import { toForecast } from "@/lib/weather/actor-items";
import { getForecast } from "@/lib/weather/tools/get-forecast";
import { LatitudeSchema, LongitudeSchema, type WeatherTool } from "@/lib/weather/weather-tool";

/** What the Actor tool needs to run: the Apify client, the call's abort signal, and the request's logger. */
export type ActorToolContext = { apify: ApifyClient; signal?: AbortSignal; log?: Logger };

const ActorInputSchema: z.ZodType<ActorForecastInput> = z.object({
  locations: z
    .array(
      z.object({
        name: z.string().min(1).max(MAX_QUERY_CHARS).describe("The place's name, as geocode_location found it."),
        latitude: LatitudeSchema,
        longitude: LongitudeSchema,
      }),
    )
    .length(1)
    .describe("The one place to forecast: its name and coordinates, from geocode_location."),
  forecastDays: z
    .number()
    .int()
    .min(1)
    .max(MAX_FORECAST_DAYS)
    .describe(`How many days, counting today in that place: 1 to ${MAX_FORECAST_DAYS}.`),
  mode: z
    .enum(["daily", "hourly"])
    .describe(`daily: one record per day. hourly: also each hour of the first ${MAX_HOURLY_DAYS} days.`),
  units: z.enum(["metric", "imperial"]).describe("metric: °C. imperial: °F."),
});

export const openMeteoActor: WeatherTool<typeof ACTOR_TOOL_NAME, ActorForecastInput, Forecast, ActorToolContext> = {
  name: ACTOR_TOOL_NAME,
  description:
    "Gives the forecast for one place by running the Open-Meteo Weather Forecast Actor on Apify: per day (condition, " +
    "lowest and highest temperature, the highest chance of rain, sunrise, sunset) and, in hourly mode, per hour. " +
    "Give the place's name and coordinates from geocode_location. The first day is today in that place; times are " +
    "local.",
  inputSchema: ActorInputSchema,
  async run({ locations, forecastDays, mode, units }, { apify, signal, log }) {
    // The Actor gets its own three fields, with the coordinates rounded to about 1 km, as Open-Meteo's are.
    const rounded = locations.map(({ name, latitude, longitude }) => ({
      name,
      latitude: roundCoordinate(latitude),
      longitude: roundCoordinate(longitude),
    }));
    const run = await apify.runActor({ locations: rounded, forecastDays, mode }, { signal, log });
    return { output: toForecast(run.items, { units, fetchedAt: run.fetchedAt }), request: run.request, cache: "miss" };
  },
  // The same result as get_forecast, so the same one-line summary.
  summarize: (forecast) => getForecast.summarize(forecast),
};
