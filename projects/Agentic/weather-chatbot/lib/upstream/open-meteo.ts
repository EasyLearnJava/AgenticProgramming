/*
 * lib/upstream/open-meteo.ts: the calls to Open-Meteo's three APIs (geocoding, forecast, air quality), with fetch:
 * rounded coordinates, timezone=auto, 3 s a try and one retry, Retry-After on a 429, and the Runtime Cache. Open-Meteo's
 * own field names (temperature_2m, country_code) stay in this file: its schemas rename them once, to ours.
 */
import "server-only";
import { getCache } from "@vercel/functions";
import { z } from "zod";
import {
  AIR_QUALITY_CACHE_TTL_SECONDS,
  COORDINATE_DECIMALS,
  CURRENT_WEATHER_CACHE_TTL_SECONDS,
  FORECAST_CACHE_TTL_SECONDS,
  GEOCODE_CACHE_TTL_SECONDS,
  MAX_HOURLY_DAYS,
  OPEN_METEO_AIR_QUALITY_URL,
  OPEN_METEO_FORECAST_URL,
  OPEN_METEO_GEOCODING_URL,
  OPEN_METEO_TRIES,
  OPEN_METEO_TRY_TIMEOUT_MS,
  RETRY_AFTER_MAX_MS,
  RETRY_WAIT_MAX_MS,
} from "@/lib/constants";
import { ContractError, UpstreamRateLimitedError, UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import type { Place, Units, WireRequest } from "@/lib/types";
import { roundCoordinate, timeoutSignal, toAbortKind, toRetryAfterMs, withRetry } from "@/lib/utils";

const HOURS_PER_DAY = 24;
const HTTP_TOO_MANY_REQUESTS = 429;
const HTTP_SERVER_ERROR = 500;

// ① What Open-Meteo sends back, checked with Zod, and renamed to our names.

const GeocodingResponseSchema = z
  .object({
    results: z
      .array(
        z.object({
          name: z.string(),
          admin1: z.string().optional(),
          country: z.string().optional(),
          country_code: z.string().optional(),
          latitude: z.number(),
          longitude: z.number(),
          timezone: z.string().optional(),
          population: z.number().optional(),
        }),
      )
      .optional(),
  })
  .transform(({ results = [] }): Place[] =>
    results.map((result) => ({
      name: result.name,
      region: result.admin1,
      country: result.country,
      countryCode: result.country_code,
      latitude: result.latitude,
      longitude: result.longitude,
      timeZone: result.timezone,
      population: result.population,
    })),
  );

const numbers = z.array(z.number().nullable());
const times = z.array(z.string());

const ForecastResponseSchema = z
  .object({
    timezone: z.string(),
    daily_units: z.object({ temperature_2m_max: z.string() }),
    daily: z.object({
      time: times,
      weather_code: numbers,
      temperature_2m_max: numbers,
      temperature_2m_min: numbers,
      precipitation_probability_max: numbers,
      sunrise: z.array(z.string().nullable()),
      sunset: z.array(z.string().nullable()),
    }),
    hourly: z
      .object({ time: times, temperature_2m: numbers, precipitation_probability: numbers, weather_code: numbers })
      .optional(),
  })
  .transform((raw) => ({
    timeZone: raw.timezone,
    temperatureUnit: raw.daily_units.temperature_2m_max,
    days: raw.daily.time.map((date, i) => ({
      date,
      weatherCode: raw.daily.weather_code[i] ?? null,
      temperatureMax: raw.daily.temperature_2m_max[i] ?? null,
      temperatureMin: raw.daily.temperature_2m_min[i] ?? null,
      rainChancePercent: raw.daily.precipitation_probability_max[i] ?? null,
      sunrise: raw.daily.sunrise[i] ?? null,
      sunset: raw.daily.sunset[i] ?? null,
    })),
    hours: raw.hourly?.time.map((time, i) => ({
      time,
      temperature: raw.hourly?.temperature_2m[i] ?? null,
      rainChancePercent: raw.hourly?.precipitation_probability[i] ?? null,
      weatherCode: raw.hourly?.weather_code[i] ?? null,
    })),
  }));

const CurrentResponseSchema = z
  .object({
    timezone: z.string(),
    current_units: z.object({ temperature_2m: z.string(), wind_speed_10m: z.string() }),
    current: z.object({
      time: z.string(),
      temperature_2m: z.number().nullable(),
      apparent_temperature: z.number().nullable(),
      is_day: z.number(),
      weather_code: z.number().nullable(),
      wind_speed_10m: z.number().nullable(),
    }),
  })
  .transform((raw) => ({
    timeZone: raw.timezone,
    temperatureUnit: raw.current_units.temperature_2m,
    windSpeedUnit: raw.current_units.wind_speed_10m,
    observedAt: raw.current.time,
    temperature: raw.current.temperature_2m,
    feelsLike: raw.current.apparent_temperature,
    isDay: raw.current.is_day === 1,
    weatherCode: raw.current.weather_code,
    windSpeed: raw.current.wind_speed_10m,
  }));

const AirQualityResponseSchema = z
  .object({
    timezone: z.string(),
    current: z.object({
      time: z.string(),
      pm2_5: z.number().nullable(),
      pm10: z.number().nullable(),
      european_aqi: z.number().nullable(),
      us_aqi: z.number().nullable(),
    }),
  })
  .transform((raw) => ({
    timeZone: raw.timezone,
    observedAt: raw.current.time,
    pm25: raw.current.pm2_5,
    pm10: raw.current.pm10,
    europeanAqi: raw.current.european_aqi,
    usAqi: raw.current.us_aqi,
  }));

export type ForecastData = z.output<typeof ForecastResponseSchema>;
export type CurrentData = z.output<typeof CurrentResponseSchema>;
export type AirQualityData = z.output<typeof AirQualityResponseSchema>;

// ② The requests, built from the tools' inputs: coordinates rounded to about 1 km, and the place's own time zone.

type Coordinates = { latitude: number; longitude: number };

const IMPERIAL_PARAMS = { temperature_unit: "fahrenheit", wind_speed_unit: "mph", precipitation_unit: "inch" };

/** The query string for a point: its coordinates, rounded to 2 decimals. */
function toPointParams({ latitude, longitude }: Coordinates): Record<string, string> {
  return {
    latitude: String(roundCoordinate(latitude, COORDINATE_DECIMALS)),
    longitude: String(roundCoordinate(longitude, COORDINATE_DECIMALS)),
  };
}

/** A GET request to one of Open-Meteo's APIs. Commas stay as they are, as in Open-Meteo's own examples. */
function toGetRequest(baseUrl: string, params: Record<string, string>): WireRequest {
  const query = new URLSearchParams(params).toString().replaceAll("%2C", ",");
  return { method: "GET", url: `${baseUrl}?${query}`, headers: { accept: "application/json" } };
}

/** The geocoding search for a name, in English. */
function toGeocodingRequest(query: string, count: number, countryCode?: string): WireRequest {
  return toGetRequest(OPEN_METEO_GEOCODING_URL, {
    name: query,
    count: String(count),
    language: "en",
    format: "json",
    ...(countryCode ? { countryCode: countryCode.toUpperCase() } : {}),
  });
}

/** The forecast for a point: the days asked for, and their hours if asked, in the place's own time zone. */
export function toForecastRequest(
  point: Coordinates,
  { days, includeHourly, units }: { days: number; includeHourly: boolean; units: Units },
): WireRequest {
  return toGetRequest(OPEN_METEO_FORECAST_URL, {
    ...toPointParams(point),
    daily: "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
    ...(includeHourly ? { hourly: "temperature_2m,precipitation_probability,weather_code" } : {}),
    timezone: "auto",
    forecast_days: String(days),
    ...(units === "imperial" ? IMPERIAL_PARAMS : {}),
  });
}

/** The weather now at a point. */
function toCurrentRequest(point: Coordinates, units: Units): WireRequest {
  return toGetRequest(OPEN_METEO_FORECAST_URL, {
    ...toPointParams(point),
    current: "temperature_2m,apparent_temperature,is_day,weather_code,wind_speed_10m",
    timezone: "auto",
    ...(units === "imperial" ? IMPERIAL_PARAMS : {}),
  });
}

/** The air quality now at a point. */
function toAirQualityRequest(point: Coordinates): WireRequest {
  return toGetRequest(OPEN_METEO_AIR_QUALITY_URL, {
    ...toPointParams(point),
    current: "pm2_5,pm10,european_aqi,us_aqi",
    timezone: "auto",
  });
}

// ③ The client: each call checks the cache, then asks Open-Meteo, then fills the cache.

/** The cache the client uses: Vercel's Runtime Cache, or a stand-in in the tests. */
export type ResponseCache = {
  get: (key: string) => Promise<unknown>;
  set: (key: string, value: unknown, options: { ttl: number }) => Promise<void>;
};

/** One answer from Open-Meteo: our data, the request behind it, whether the cache answered, and when it was fetched. */
export type UpstreamAnswer<T> = { data: T; request: WireRequest; cache: "hit" | "miss"; fetchedAt: string };

type ForecastQuery = Coordinates & { days: number; includeHourly: boolean; units: Units };

/** The client's four calls. Each takes the tool's abort signal, so Stop and the tool's time budget cancel it. */
export type OpenMeteoClient = {
  searchPlaces: (
    input: { query: string; count: number; countryCode?: string },
    signal?: AbortSignal,
  ) => Promise<UpstreamAnswer<Place[]>>;
  getForecast: (input: ForecastQuery, signal?: AbortSignal) => Promise<UpstreamAnswer<ForecastData>>;
  getCurrentWeather: (
    input: Coordinates & { units: Units },
    signal?: AbortSignal,
  ) => Promise<UpstreamAnswer<CurrentData>>;
  getAirQuality: (input: Coordinates, signal?: AbortSignal) => Promise<UpstreamAnswer<AirQualityData>>;
};

type OpenMeteoOptions = {
  fetch?: typeof fetch;
  cache?: ResponseCache;
  now?: () => Date;
  random?: () => number;
  tryTimeoutMs?: number;
};

const CachedAnswerSchema = z.object({ body: z.unknown(), fetchedAt: z.string() });

/** Makes a client for Open-Meteo. Everything it uses comes in as an option, so the tests can pass stand-ins. */
export function createOpenMeteoClient({
  fetch: fetchJson = fetch,
  cache = getCache(),
  now = () => new Date(),
  random = Math.random,
  tryTimeoutMs = OPEN_METEO_TRY_TIMEOUT_MS,
}: OpenMeteoOptions = {}): OpenMeteoClient {
  /** One GET: the cache first; else Open-Meteo, with a second try; then the answer goes in the cache. */
  async function get<T>(
    request: WireRequest,
    schema: z.ZodType<T>,
    ttlSeconds: number,
    signal?: AbortSignal,
  ): Promise<UpstreamAnswer<T>> {
    if (signal?.aborted) {
      throw toAbortedError(signal);
    }
    const key = `open-meteo:${request.url}`;
    const cached = CachedAnswerSchema.safeParse(await cache.get(key));
    const cachedData = cached.success ? schema.safeParse(cached.data.body) : undefined;
    if (cached.success && cachedData?.success) {
      return { data: cachedData.data, request, cache: "hit", fetchedAt: cached.data.fetchedAt };
    }
    const body = await withRetry(() => fetchOnce(request, signal), {
      tries: OPEN_METEO_TRIES,
      shouldRetry: isWorthRetrying,
      waitMs: (error) =>
        error instanceof UpstreamRateLimitedError && error.retryAfterMs !== undefined
          ? error.retryAfterMs
          : random() * RETRY_WAIT_MAX_MS,
      signal,
    }).catch((error: unknown) => {
      throw signal?.aborted ? toAbortedError(signal) : error;
    });
    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      throw new ContractError("Open-Meteo's answer doesn't have the fields we asked for.");
    }
    const fetchedAt = now().toISOString();
    await cache.set(key, { body, fetchedAt }, { ttl: ttlSeconds });
    return { data: parsed.data, request, cache: "miss", fetchedAt };
  }

  /** One try: 3 s at most, with every failure turned into one of our error classes. */
  async function fetchOnce(request: WireRequest, signal?: AbortSignal): Promise<unknown> {
    const trySignal = timeoutSignal(tryTimeoutMs, signal);
    let response: Response;
    try {
      response = await fetchJson(request.url, { headers: request.headers, signal: trySignal });
    } catch (error) {
      throw toFetchError(error, trySignal, tryTimeoutMs, signal);
    }
    if (response.status === HTTP_TOO_MANY_REQUESTS) {
      throw new UpstreamRateLimitedError(
        "Open-Meteo answered 429.",
        toRetryAfterMs(response.headers.get("retry-after")),
      );
    }
    if (response.status >= HTTP_SERVER_ERROR) {
      throw new UpstreamUnavailableError(`Open-Meteo answered ${response.status}.`);
    }
    if (!response.ok) {
      throw new ContractError(`Open-Meteo refused the request with ${response.status}.`);
    }
    try {
      return await response.json();
    } catch (error) {
      throw toFetchError(error, trySignal, tryTimeoutMs, signal);
    }
  }

  return {
    searchPlaces: ({ query, count, countryCode }, signal) =>
      get(toGeocodingRequest(query, count, countryCode), GeocodingResponseSchema, GEOCODE_CACHE_TTL_SECONDS, signal),
    getForecast: async (input, signal) => {
      const request = toForecastRequest(input, input);
      const answer = await get(request, ForecastResponseSchema, FORECAST_CACHE_TTL_SECONDS, signal);
      // An hourly forecast covers the first 3 days at most, so a long one doesn't flood the model.
      const hours = answer.data.hours?.slice(0, MAX_HOURLY_DAYS * HOURS_PER_DAY);
      return { ...answer, data: { ...answer.data, hours } };
    },
    getCurrentWeather: (input, signal) =>
      get(toCurrentRequest(input, input.units), CurrentResponseSchema, CURRENT_WEATHER_CACHE_TTL_SECONDS, signal),
    getAirQuality: (input, signal) =>
      get(toAirQualityRequest(input), AirQualityResponseSchema, AIR_QUALITY_CACHE_TTL_SECONDS, signal),
  };
}

/**
 * Why the tool's own signal fired: past the tool's time budget (a TimeoutError) is UpstreamTimeoutError, like any
 * slow answer; a stop (Stop, or the answer's end) is passed on as it is.
 */
function toAbortedError(signal: AbortSignal): unknown {
  return toAbortKind(signal) === "timeout"
    ? new UpstreamTimeoutError("Open-Meteo didn't answer within the tool's time budget.")
    : signal.reason;
}

/** A failed fetch or body read, as one of our classes. A stop from the user is passed on as it is. */
function toFetchError(error: unknown, trySignal: AbortSignal, tryTimeoutMs: number, signal?: AbortSignal): unknown {
  if (signal?.aborted) {
    return toAbortedError(signal);
  }
  if (trySignal.aborted) {
    return new UpstreamTimeoutError(`Open-Meteo didn't answer within ${tryTimeoutMs} ms.`);
  }
  return error instanceof SyntaxError
    ? new ContractError("Open-Meteo's answer isn't JSON.")
    : new UpstreamUnavailableError("Open-Meteo can't be reached.");
}

/** A timeout or a 5xx is worth a second try; so is a 429 whose Retry-After fits in the tool's budget. */
function isWorthRetrying(error: unknown): boolean {
  if (error instanceof UpstreamRateLimitedError) {
    return error.retryAfterMs !== undefined && error.retryAfterMs <= RETRY_AFTER_MAX_MS;
  }
  return error instanceof UpstreamTimeoutError || error instanceof UpstreamUnavailableError;
}
