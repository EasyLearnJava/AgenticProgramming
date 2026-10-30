/*
 * lib/weather/open-meteo-tools.ts: our four weather tools, by name: the one list both no-auth doors use, so they
 * can't drift apart (PLAN.md 7.6).
 */
import "server-only";
import type { OpenMeteoToolTypes } from "@/lib/types";
import { geocodeLocation } from "@/lib/weather/tools/geocode-location";
import { getAirQuality } from "@/lib/weather/tools/get-air-quality";
import { getCurrentWeather } from "@/lib/weather/tools/get-current-weather";
import { getForecast } from "@/lib/weather/tools/get-forecast";
import type { WeatherTool } from "@/lib/weather/weather-tool";

/** Each tool under its own name, typed by the shapes in types.ts: a wrong name or shape doesn't compile. */
export type OpenMeteoTools = {
  [Name in keyof OpenMeteoToolTypes]: WeatherTool<
    Name,
    OpenMeteoToolTypes[Name]["input"],
    OpenMeteoToolTypes[Name]["output"]["result"]
  >;
};

export const OPEN_METEO_TOOLS: OpenMeteoTools = {
  geocode_location: geocodeLocation,
  get_current_weather: getCurrentWeather,
  get_forecast: getForecast,
  get_air_quality: getAirQuality,
};
