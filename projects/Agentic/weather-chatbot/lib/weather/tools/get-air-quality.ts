/*
 * lib/weather/tools/get-air-quality.ts: get_air_quality gives the air quality now at a point, from Open-Meteo's
 * air-quality API.
 */
import "server-only";
import { z } from "zod";
import type { AirQuality, AirQualityInput } from "@/lib/types";
import { roundCoordinate } from "@/lib/utils";
import { LatitudeSchema, LongitudeSchema, type WeatherTool } from "@/lib/weather/weather-tool";

const AirQualityInputSchema: z.ZodType<AirQualityInput> = z.object({
  latitude: LatitudeSchema,
  longitude: LongitudeSchema,
});

export const getAirQuality: WeatherTool<"get_air_quality", AirQualityInput, AirQuality> = {
  name: "get_air_quality",
  description:
    "Gives the air quality now at a point: PM2.5 and PM10 in μg/m³, the European AQI and the US AQI, and when it was " +
    "observed, in the place's local time.",
  inputSchema: AirQualityInputSchema,
  async run(input, { openMeteo, signal }) {
    const answer = await openMeteo.getAirQuality(input, signal);
    const output: AirQuality = {
      ...answer.data,
      latitude: roundCoordinate(input.latitude),
      longitude: roundCoordinate(input.longitude),
      fetchedAt: answer.fetchedAt,
    };
    return { output, request: answer.request, cache: answer.cache };
  },
  summarize({ usAqi, europeanAqi }) {
    return `US AQI ${usAqi ?? "unknown"} · European AQI ${europeanAqi ?? "unknown"}`;
  },
};
