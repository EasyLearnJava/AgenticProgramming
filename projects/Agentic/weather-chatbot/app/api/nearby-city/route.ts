/*
 * app/api/nearby-city/route.ts: GET /api/nearby-city, which the chat page calls once: the city Vercel places this
 * visitor's network in, from its location headers, for one suggested question. It's only ever offered, never used
 * as a default; off Vercel there's no city.
 */
import { geolocation } from "@vercel/functions";

/** The nearby city's name, or null when Vercel doesn't know it; never stored, and private to this visitor. */
export function GET(request: Request): Response {
  const { city } = geolocation(request);
  return Response.json({ city: city ?? null }, { headers: { "cache-control": "private, no-store" } });
}
