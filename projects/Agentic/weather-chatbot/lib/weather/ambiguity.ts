/*
 * lib/weather/ambiguity.ts: the ambiguity rule (PLAN.md 7.6), in code rather than left to the model: may a place
 * name mean more than one place, so the bot should ask which one?
 */
import "server-only";
import type { Place } from "@/lib/types";

// A rival place makes the name ambiguous when the largest place has at most 3 times its population.
const LARGEST_TO_RIVAL_MAX_RATIO = 3;

/** Whether two places are in different regions: another first-level region (a state, say), or another country. */
function isElsewhere(place: Place, other: Place): boolean {
  return place.region !== other.region || place.countryCode !== other.countryCode;
}

/**
 * True when the largest place elsewhere has at least a third of the largest place's population, or when the largest
 * place's population is unknown and there's a place elsewhere. Open-Meteo doesn't sort by population, so this does.
 */
export function isAmbiguousPlace(candidates: readonly Place[]): boolean {
  const [largest, ...others] = [...candidates].sort((a, b) => (b.population ?? -1) - (a.population ?? -1));
  if (largest === undefined) {
    return false;
  }
  const rival = others.find((other) => isElsewhere(largest, other));
  if (rival === undefined) {
    return false;
  }
  if (largest.population === undefined) {
    return true;
  }
  return largest.population <= (rival.population ?? 0) * LARGEST_TO_RIVAL_MAX_RATIO;
}
