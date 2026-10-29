/*
 * lib/weather/tools/geocode-location.ts: geocode_location finds places by name, with Open-Meteo's geocoding, and says
 * whether the name is ambiguous (PLAN.md 7.6).
 */
import "server-only";
import { z } from "zod";
import { DEFAULT_PLACE_COUNT, MAX_PLACE_COUNT, MAX_QUERY_CHARS } from "@/lib/constants";
import type { GeocodeInput, GeocodeResult, Place } from "@/lib/types";
import { roundCoordinate } from "@/lib/utils";
import { isAmbiguousPlace } from "@/lib/weather/ambiguity";
import type { WeatherTool } from "@/lib/weather/weather-tool";

const GeocodeInputSchema: z.ZodType<GeocodeInput> = z.object({
  query: z
    .string()
    .trim()
    .min(1)
    .max(MAX_QUERY_CHARS)
    .describe("The place's name. Put a region or country after a comma to narrow it: 'Springfield, MA'."),
  count: z
    .number()
    .int()
    .min(1)
    .max(MAX_PLACE_COUNT)
    .optional()
    .describe(`How many places to return, 1 to ${MAX_PLACE_COUNT}; ${DEFAULT_PLACE_COUNT} if left out.`),
  countryCode: z
    .string()
    .regex(/^[A-Za-z]{2}$/)
    .optional()
    .describe("An ISO 3166-1 alpha-2 country code, such as 'US', to search that country only."),
});

/** A place, in a few words: "Paris, Île-de-France Region, FR · 48.85, 2.35". */
function toPlaceLine(place: Place): string {
  const name = [place.name, place.region, place.countryCode].filter(Boolean).join(", ");
  return `${name} · ${roundCoordinate(place.latitude)}, ${roundCoordinate(place.longitude)}`;
}

export const geocodeLocation: WeatherTool<"geocode_location", GeocodeInput, GeocodeResult> = {
  name: "geocode_location",
  description:
    "Finds places by name. Returns the candidates (name, region, country, coordinates, time zone, population) and " +
    "isAmbiguous: true when the name could mean more than one place. An empty list means no place has that name.",
  inputSchema: GeocodeInputSchema,
  async run({ query, count = DEFAULT_PLACE_COUNT, countryCode }, { openMeteo, signal, log }) {
    const answer = await openMeteo.searchPlaces({ query, count, countryCode }, { signal, log });
    const output = { candidates: answer.data, isAmbiguous: isAmbiguousPlace(answer.data) };
    return { output, request: answer.request, cache: answer.cache };
  },
  summarize({ candidates, isAmbiguous }) {
    const [first] = candidates;
    if (first === undefined) {
      return "No place found";
    }
    return isAmbiguous ? `${candidates.length} places, ambiguous` : toPlaceLine(first);
  },
};
