/*
 * lib/weather/tools/get-current-weather.ts: get_current_weather gives the weather now at a point, from Open-Meteo's
 * forecast API.
 */
import "server-only";
import { z } from "zod";
import type { CurrentWeather, CurrentWeatherInput } from "@/lib/types";
import { roundCoordinate } from "@/lib/utils";
import { LatitudeSchema, LongitudeSchema, type WeatherTool } from "@/lib/weather/weather-tool";
import { toCondition } from "@/lib/weather/wmo-codes";

const CurrentWeatherInputSchema: z.ZodType<CurrentWeatherInput> = z.object({
  latitude: LatitudeSchema,
  longitude: LongitudeSchema,
  units: z.enum(["metric", "imperial"]).describe("metric: °C, km/h. imperial: °F, mph."),
});

export const getCurrentWeather: WeatherTool<"get_current_weather", CurrentWeatherInput, CurrentWeather> = {
  name: "get_current_weather",
  description:
    "Gives the weather now at a point: temperature, feels-like temperature, wind, the condition, day or night, and " +
    "when it was observed, in the place's local time.",
  inputSchema: CurrentWeatherInputSchema,
  async run(input, { openMeteo, signal, log }) {
    const answer = await openMeteo.getCurrentWeather(input, { signal, log });
    const { weatherCode, ...now } = answer.data;
    const condition = toCondition(weatherCode);
    const output: CurrentWeather = {
      ...now,
      latitude: roundCoordinate(input.latitude),
      longitude: roundCoordinate(input.longitude),
      condition: condition.words,
      icon: condition.icon,
      fetchedAt: answer.fetchedAt,
    };
    return { output, request: answer.request, cache: answer.cache };
  },
  summarize({ temperature, temperatureUnit, condition }) {
    return temperature === null
      ? condition
      : `${Math.round(temperature)} ${temperatureUnit}, ${condition.toLowerCase()}`;
  },
};
