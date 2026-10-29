/*
 * hooks/use-nearby-city.ts: asks /api/nearby-city, once, for the city Vercel places this visitor in, so the first
 * message can suggest a question about it. Without a city (on a laptop, or if the call fails) there's no suggestion,
 * and nothing else depends on it.
 */
"use client";

import { useEffect, useState } from "react";
import { NEARBY_CITY_API_PATH } from "@/lib/constants";

/** The nearby city's name, once it's known; undefined until then, or when there's none. */
export function useNearbyCity(): string | undefined {
  const [city, setCity] = useState<string | undefined>(undefined);
  useEffect(() => {
    const controller = new AbortController();
    fetch(NEARBY_CITY_API_PATH, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: unknown) => {
        const named = typeof body === "object" && body !== null && "city" in body ? body.city : null;
        setCity(typeof named === "string" && named !== "" ? named : undefined);
      })
      .catch(() => setCity(undefined));
    return () => controller.abort();
  }, []);
  return city;
}
