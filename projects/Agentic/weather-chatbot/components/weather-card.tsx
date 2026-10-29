/*
 * components/weather-card.tsx: the card under a forecast answer: the place, the period, a bar per hour for the chance
 * of rain, and the data's source.
 */
import type { ReactNode } from "react";
import type { ForecastView } from "@/lib/types";

type WeatherCardProps = { forecast: ForecastView };

/** The forecast at a glance; the bars' values are written out for screen readers. */
export function WeatherCard({ forecast }: WeatherCardProps): ReactNode {
  return (
    <section className="weather-card" aria-label={`Forecast for ${forecast.place}`}>
      <p className="weather-card-place">{forecast.place}</p>
      <p className="weather-card-period">{forecast.period}</p>
      <p className="weather-card-summary">
        {forecast.condition} · {forecast.temperatureRange} · sunset {forecast.sunset}
      </p>
      <ol className="rain-bars" aria-label="Chance of rain, by hour">
        {forecast.hourlyRain.map((hour) => (
          <li key={hour.hour} className="rain-bar">
            <span className="rain-bar-track" aria-hidden="true">
              <span className="rain-bar-fill" style={{ height: `${hour.chancePercent}%` }} />
            </span>
            <span className="rain-bar-value">{hour.chancePercent}%</span>
            <span className="rain-bar-hour">{hour.hour}</span>
          </li>
        ))}
      </ol>
      <p className="weather-card-credit">
        Weather data by <a href="https://open-meteo.com/">Open-Meteo.com</a> · {forecast.fetched}
      </p>
    </section>
  );
}
