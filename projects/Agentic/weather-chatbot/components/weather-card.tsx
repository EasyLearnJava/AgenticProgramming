/*
 * components/weather-card.tsx: the card under a forecast answer: the place, a row per day with its condition,
 * temperatures and chance of rain, and the data's source and age.
 */
import type { ReactNode } from "react";
import type { Forecast, ForecastDay } from "@/lib/types";
import { formatLocalTime } from "@/lib/utils";

type WeatherCardProps = { forecast: Forecast; placeName: string | undefined };

/** A day's lowest and highest temperatures, rounded: "6 to 15 °C". */
function toTemperatureRange(day: ForecastDay, unit: string): string {
  if (day.temperatureMin === null || day.temperatureMax === null) {
    return "temperature unknown";
  }
  return `${Math.round(day.temperatureMin)} to ${Math.round(day.temperatureMax)} ${unit}`;
}

/** The forecast at a glance; each bar's value is written out, for screen readers too. */
export function WeatherCard({ forecast, placeName }: WeatherCardProps): ReactNode {
  const place = placeName ?? `${forecast.latitude}, ${forecast.longitude}`;
  return (
    <section className="weather-card" aria-label={`Forecast for ${place}`}>
      <p className="weather-card-place">{place}</p>
      <p className="weather-card-period">Times in {forecast.timeZone}</p>
      <ol className="forecast-days">
        {forecast.days.map((day) => (
          <li key={day.date} className="forecast-day">
            <span className="forecast-day-name">
              {day.weekday} {Number(day.date.slice(-2))}
            </span>
            <span className="forecast-day-condition">
              <span aria-hidden="true">{day.icon}</span> {day.condition}
            </span>
            <span className="forecast-day-temperature">{toTemperatureRange(day, forecast.temperatureUnit)}</span>
            <span className="forecast-day-rain">
              <span className="rain-meter" aria-hidden="true">
                <span className="rain-meter-fill" style={{ width: `${day.rainChancePercent ?? 0}%` }} />
              </span>
              {day.rainChancePercent === null ? "rain unknown" : `${day.rainChancePercent}% rain`}
            </span>
          </li>
        ))}
      </ol>
      <p className="weather-card-credit">
        Weather data by <a href="https://open-meteo.com/">Open-Meteo.com</a> · fetched at{" "}
        {formatLocalTime(forecast.fetchedAt, forecast.timeZone)}, local time
      </p>
    </section>
  );
}
