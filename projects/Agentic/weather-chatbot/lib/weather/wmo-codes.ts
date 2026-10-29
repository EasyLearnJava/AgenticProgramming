/*
 * lib/weather/wmo-codes.ts: the WMO weather codes Open-Meteo uses (0 clear sky, 1 mainly clear, ...), as words and an
 * icon, from this one table: the words in an answer never come from the model's memory.
 */
import "server-only";

type Condition = { words: string; icon: string };

// The codes and words are WMO's, as Open-Meteo's documentation lists them (open-meteo.com/en/docs, "WMO Weather
// interpretation codes").
const CONDITION_BY_CODE: Readonly<Record<number, Condition>> = {
  0: { words: "Clear sky", icon: "☀️" },
  1: { words: "Mainly clear", icon: "🌤️" },
  2: { words: "Partly cloudy", icon: "⛅" },
  3: { words: "Overcast", icon: "☁️" },
  45: { words: "Fog", icon: "🌫️" },
  48: { words: "Depositing rime fog", icon: "🌫️" },
  51: { words: "Light drizzle", icon: "🌦️" },
  53: { words: "Moderate drizzle", icon: "🌦️" },
  55: { words: "Dense drizzle", icon: "🌧️" },
  56: { words: "Light freezing drizzle", icon: "🌧️" },
  57: { words: "Dense freezing drizzle", icon: "🌧️" },
  61: { words: "Slight rain", icon: "🌦️" },
  63: { words: "Moderate rain", icon: "🌧️" },
  65: { words: "Heavy rain", icon: "🌧️" },
  66: { words: "Light freezing rain", icon: "🌧️" },
  67: { words: "Heavy freezing rain", icon: "🌧️" },
  71: { words: "Slight snowfall", icon: "🌨️" },
  73: { words: "Moderate snowfall", icon: "🌨️" },
  75: { words: "Heavy snowfall", icon: "❄️" },
  77: { words: "Snow grains", icon: "🌨️" },
  80: { words: "Slight rain showers", icon: "🌦️" },
  81: { words: "Moderate rain showers", icon: "🌧️" },
  82: { words: "Violent rain showers", icon: "⛈️" },
  85: { words: "Slight snow showers", icon: "🌨️" },
  86: { words: "Heavy snow showers", icon: "❄️" },
  95: { words: "Thunderstorm", icon: "⛈️" },
  96: { words: "Thunderstorm with slight hail", icon: "⛈️" },
  99: { words: "Thunderstorm with heavy hail", icon: "⛈️" },
};

/** A WMO code as words and an icon; a code that isn't in the table, or a missing one, says so. */
export function toCondition(code: number | null): Condition {
  if (code === null) {
    return { words: "Unknown conditions", icon: "❔" };
  }
  return CONDITION_BY_CODE[code] ?? { words: `Unknown conditions (WMO code ${code})`, icon: "❔" };
}
