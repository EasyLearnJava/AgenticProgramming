/*
 * tests/unit/upstream/open-meteo.test.ts: the Open-Meteo client against Open-Meteo's recorded answers (29 October
 * 2026): the requests it sends, our names for the fields, the cache, the retry, every failure, and its log lines.
 */
import { describe, expect, it } from "vitest";
import { ContractError, UpstreamRateLimitedError, UpstreamTimeoutError, UpstreamUnavailableError } from "@/lib/errors";
import { createOpenMeteoClient, toForecastRequest } from "@/lib/upstream/open-meteo";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createFakeFetch, createMemoryCache, hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

const NOW = new Date("2026-10-29T16:00:00Z");
const PARIS = { latitude: 48.85341, longitude: 2.3488 };
const PARIS_FORECAST = { ...PARIS, days: 2, includeHourly: true, units: "metric" as const };

/** A client with stand-ins: the given answers, an empty cache, no waiting between tries. */
function clientWith(answers: Parameters<typeof createFakeFetch>[0], tryTimeoutMs = 3000) {
  const fake = createFakeFetch(answers);
  const cache = createMemoryCache();
  const client = createOpenMeteoClient({ fetch: fake.fetch, cache, now: () => NOW, random: () => 0, tryTimeoutMs });
  return { client, cache, urls: fake.urls, headers: fake.headers };
}

describe("the requests", () => {
  it("rounds the coordinates to 2 decimals and asks for the place's own time zone", () => {
    expect(toForecastRequest(PARIS, { days: 2, includeHourly: true, units: "metric" }).url).toBe(
      "https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35" +
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset" +
        "&hourly=temperature_2m,precipitation_probability,weather_code&timezone=auto&forecast_days=2",
    );
  });

  it("asks Open-Meteo for imperial units, and leaves the hours out unless asked", () => {
    const { url } = toForecastRequest(
      { latitude: 32.78, longitude: -96.8 },
      { days: 2, includeHourly: false, units: "imperial" },
    );
    expect(url).toContain("temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch");
    expect(url).not.toContain("hourly=");
  });

  it("records the request exactly as it sends it, headers included, for the wire view", async () => {
    const { client, urls, headers } = clientWith([{ fixture: "geocode-paris" }]);
    const answer = await client.searchPlaces({ query: "Paris", count: 5 });
    expect(answer.request).toEqual({ method: "GET", url: urls[0], headers: headers[0] });
    expect(headers[0]).toEqual({ accept: "application/json" });
  });

  it("searches places in English, with the country code in capitals", async () => {
    const { client, urls } = clientWith([{ fixture: "geocode-springfield-ma" }]);
    await client.searchPlaces({ query: "Springfield, MA", count: 5, countryCode: "us" });
    expect(urls[0]).toBe(
      "https://geocoding-api.open-meteo.com/v1/search?name=Springfield,+MA&count=5&language=en&format=json&countryCode=US",
    );
  });
});

describe("the answers, in our names", () => {
  it("gives each place's name, region, country, coordinates, time zone and population", async () => {
    const { client } = clientWith([{ fixture: "geocode-paris" }]);
    const { data } = await client.searchPlaces({ query: "Paris", count: 5 });
    expect(data).toHaveLength(5);
    expect(data[0]).toEqual({
      name: "Paris",
      region: "Île-de-France Region",
      country: "France",
      countryCode: "FR",
      latitude: 48.85341,
      longitude: 2.3488,
      timeZone: "Europe/Paris",
      population: 2138551,
    });
  });

  it("gives an empty list for a name no place has", async () => {
    const { client } = clientWith([{ fixture: "geocode-hogwarts" }]);
    expect((await client.searchPlaces({ query: "Hogwarts", count: 5 })).data).toEqual([]);
  });

  it("gives the forecast per day and per hour, in the place's local time", async () => {
    const { client } = clientWith([{ fixture: "forecast-paris" }]);
    const { data } = await client.getForecast(PARIS_FORECAST);
    expect(data.timeZone).toBe("Europe/Paris");
    expect(data.temperatureUnit).toBe("°C");
    expect(data.days[1]).toEqual({
      date: "2026-10-30",
      weatherCode: 1,
      temperatureMax: 15.3,
      temperatureMin: 6.1,
      rainChancePercent: 0,
      sunrise: "2026-10-30T07:34",
      sunset: "2026-10-30T17:33",
    });
    expect(data.hours).toHaveLength(48);
    expect(data.hours?.[36]).toEqual({
      time: "2026-10-30T12:00",
      temperature: 12.1,
      rainChancePercent: 0,
      weatherCode: 0,
    });
  });

  it("gives the weather now, and the air quality now", async () => {
    const { client } = clientWith([{ fixture: "current-tokyo" }, { fixture: "air-delhi" }]);
    const now = await client.getCurrentWeather({ latitude: 35.69, longitude: 139.69, units: "metric" });
    expect(now.data).toMatchObject({
      timeZone: "Asia/Tokyo",
      observedAt: "2026-10-30T04:00",
      temperature: 12,
      isDay: false,
    });
    const air = await client.getAirQuality({ latitude: 28.65, longitude: 77.23 });
    expect(air.data).toMatchObject({ timeZone: "Asia/Kolkata", pm25: 23.2, pm10: 25.8, europeanAqi: 45, usAqi: 131 });
  });
});

describe("the cache", () => {
  it("answers the second same request from the cache, with the first one's time", async () => {
    const { client, cache, urls } = clientWith([{ fixture: "forecast-paris" }]);
    const first = await client.getForecast(PARIS_FORECAST);
    const second = await client.getForecast(PARIS_FORECAST);
    expect(urls).toHaveLength(1);
    expect([first.cache, second.cache]).toEqual(["miss", "hit"]);
    expect(second.fetchedAt).toBe(NOW.toISOString());
    expect([...cache.entries.values()][0]?.ttl).toBe(30 * 60);
  });
});

describe("the failures", () => {
  it("tries a second time after a 5xx", async () => {
    const { client, urls } = clientWith([() => new Response("", { status: 503 }), { fixture: "geocode-paris" }]);
    expect((await client.searchPlaces({ query: "Paris", count: 5 })).data).toHaveLength(5);
    expect(urls).toHaveLength(2);
  });

  it("gives up with UpstreamUnavailableError after two 5xx", async () => {
    const fail = () => new Response("", { status: 502 });
    const { client } = clientWith([fail, fail]);
    await expect(client.searchPlaces({ query: "Paris", count: 5 })).rejects.toBeInstanceOf(UpstreamUnavailableError);
  });

  it("gives up with UpstreamTimeoutError when no try answers in time", async () => {
    const client = createOpenMeteoClient({
      fetch: hangingFetch,
      cache: createMemoryCache(),
      random: () => 0,
      tryTimeoutMs: 20,
    });
    await expect(client.searchPlaces({ query: "Paris", count: 5 })).rejects.toBeInstanceOf(UpstreamTimeoutError);
  });

  it("waits out a short Retry-After on a 429, and doesn't retry a long one", async () => {
    const short = clientWith([
      { fixture: "geocode-paris", status: 429, headers: { "retry-after": "0" } },
      { fixture: "geocode-paris" },
    ]);
    expect((await short.client.searchPlaces({ query: "Paris", count: 5 })).data).toHaveLength(5);
    const long = clientWith([{ fixture: "geocode-paris", status: 429, headers: { "retry-after": "60" } }]);
    const error = await long.client.searchPlaces({ query: "Paris", count: 5 }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(UpstreamRateLimitedError);
    expect((error as UpstreamRateLimitedError).retryAfterMs).toBe(60_000);
    expect(long.urls).toHaveLength(1);
  });

  it("turns Open-Meteo's 400 into ContractError, without its text, and doesn't retry it", async () => {
    const { client, urls } = clientWith([{ fixture: "error-17-days", status: 400 }]);
    const error = await client.getForecast({ ...PARIS_FORECAST, days: 17 }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as Error).message).toBe("Open-Meteo refused the request with 400.");
    expect(urls).toHaveLength(1);
  });

  it("turns an answer without the fields we asked for into ContractError", async () => {
    const { client } = clientWith([{ fixture: "current-tokyo" }]);
    await expect(client.getForecast(PARIS_FORECAST)).rejects.toBeInstanceOf(ContractError);
  });

  it("turns the tool's own time budget into UpstreamTimeoutError, as for any slow answer", async () => {
    const client = createOpenMeteoClient({ fetch: hangingFetch, cache: createMemoryCache(), random: () => 0 });
    const error = await client
      .searchPlaces({ query: "Paris", count: 5 }, { signal: AbortSignal.timeout(20) })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(UpstreamTimeoutError);
    expect((error as Error).message).toBe("Open-Meteo didn't answer within the tool's time budget.");
  });

  it("passes a stop from the user on as it is, without retrying", async () => {
    const controller = new AbortController();
    const client = createOpenMeteoClient({ fetch: hangingFetch, cache: createMemoryCache(), random: () => 0 });
    const pending = client.searchPlaces({ query: "Paris", count: 5 }, { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("the log lines", () => {
  it("writes one upstream.http line for each request that goes out: the host, the status, the time, the tries", async () => {
    const { client } = clientWith([{ fixture: "geocode-paris" }]);
    const { log, lines } = createTestLog();
    await client.searchPlaces({ query: "Paris", count: 5 }, { log });
    await client.searchPlaces({ query: "Paris", count: 5 }, { log });
    expect(lines).toEqual([
      expect.objectContaining({
        level: "info",
        event: "upstream.http",
        upstream: "open-meteo",
        host: "geocoding-api.open-meteo.com",
        status: "ok",
        httpStatus: 200,
        attempts: 1,
        ms: expect.any(Number),
      }),
    ]);
  });

  it("makes a retry a warning, and says only a failure's class (the tool's line says the rest)", async () => {
    const fail = () => new Response("", { status: 503 });
    const { log, lines } = createTestLog();
    await clientWith([fail, { fixture: "geocode-paris" }]).client.searchPlaces({ query: "Paris", count: 5 }, { log });
    await clientWith([fail, fail])
      .client.searchPlaces({ query: "Paris", count: 5 }, { log })
      .catch(() => undefined);
    expect(lines.map((line) => [line.level, line.status, line.attempts, line.errorClass])).toEqual([
      ["warn", "ok", 2, undefined],
      ["info", "failed", 2, "UpstreamUnavailableError"],
    ]);
  });

  it("logs nothing for a stop", async () => {
    const controller = new AbortController();
    const client = createOpenMeteoClient({ fetch: hangingFetch, cache: createMemoryCache(), random: () => 0 });
    const { log, lines } = createTestLog();
    const pending = client.searchPlaces({ query: "Paris", count: 5 }, { signal: controller.signal, log });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(lines).toEqual([]);
  });
});
