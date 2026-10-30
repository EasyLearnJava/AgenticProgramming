/*
 * tests/unit/weather/actor-items.test.ts: the Actor's items as our Forecast, against the Actor's answer for Paris in
 * its assumed shape (tests/fixtures/apify/), which holds Open-Meteo's real Paris answer: the same days and hours as
 * get_forecast gives for that answer, °F when asked, and a ContractError for any other shape, naming the field only.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ContractError } from "@/lib/errors";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { toForecast } from "@/lib/weather/actor-items";
import { getForecast } from "@/lib/weather/tools/get-forecast";
import { createFakeFetch, createMemoryCache } from "@/tests/stubs/open-meteo-stand-ins";

const FETCHED_AT = "2026-10-29T16:00:00.000Z";
const ITEMS: unknown[] = JSON.parse(
  readFileSync(path.join(import.meta.dirname, "..", "..", "fixtures", "apify", "actor-paris-assumed.json"), "utf8"),
);
const [ITEM] = ITEMS as Record<string, unknown>[];

/** The Actor's item with some of its fields changed. */
function itemWith(fields: Record<string, unknown>): unknown[] {
  return [{ ...ITEM, ...fields }];
}

describe("toForecast", () => {
  it("gives the same days and hours as get_forecast does for the same Open-Meteo answer", async () => {
    const openMeteo = createOpenMeteoClient({
      fetch: createFakeFetch([{ fixture: "forecast-paris" }]).fetch,
      cache: createMemoryCache(),
      random: () => 0,
    });
    const viaOpenMeteo = await getForecast.run(
      { latitude: 48.85341, longitude: 2.3488, days: 2, includeHourly: true, units: "metric" },
      { openMeteo },
    );
    const viaActor = toForecast(ITEMS, { units: "metric", fetchedAt: FETCHED_AT });
    expect(viaActor.days).toEqual(viaOpenMeteo.output.days);
    expect(viaActor.hours).toEqual(viaOpenMeteo.output.hours);
    expect(viaActor).toMatchObject({
      latitude: 48.85,
      longitude: 2.35,
      timeZone: "Europe/Paris",
      temperatureUnit: "°C",
    });
    expect(viaActor.fetchedAt).toBe(FETCHED_AT);
  });

  it("gives °F when asked, since the Actor answers in °C only", () => {
    const metric = toForecast(ITEMS, { units: "metric", fetchedAt: FETCHED_AT });
    const imperial = toForecast(ITEMS, { units: "imperial", fetchedAt: FETCHED_AT });
    expect(imperial.temperatureUnit).toBe("°F");
    expect([metric.days[0]?.temperatureMax, imperial.days[0]?.temperatureMax]).toEqual([15.6, 60.1]);
    expect(imperial.days[0]?.rainChancePercent).toBe(metric.days[0]?.rainChancePercent);
  });

  it("refuses any other shape, naming the field and never its value", () => {
    const refusals: [unknown[], string][] = [
      [[], "The Actor gave 0 items for one location."],
      [[ITEM, ITEM], "The Actor gave 2 items for one location."],
      [
        itemWith({ daily: undefined, hourly: undefined }),
        "The Actor's item isn't the shape we read: no daily or hourly data.",
      ],
      [itemWith({ timezone: 42 }), "The Actor's item isn't the shape we read: timezone."],
      [
        itemWith({ daily: { ...(ITEM?.daily as object), time: [1, 2] } }),
        "The Actor's item isn't the shape we read: daily.time.",
      ],
      [itemWith({ daily_units: { temperature_2m_max: "°F" } }), "The Actor's temperature unit isn't °C."],
    ];
    for (const [items, message] of refusals) {
      const error = (() => {
        try {
          toForecast(items, { units: "metric", fetchedAt: FETCHED_AT });
        } catch (caught) {
          return caught;
        }
        return undefined;
      })();
      expect(error).toBeInstanceOf(ContractError);
      expect((error as Error).message).toBe(message);
    }
  });
});
