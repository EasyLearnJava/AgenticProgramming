"""
nimbus/weather.py: what the tools decide in code rather than leave to the model: the words for each WMO weather code
Open-Meteo gives (0 is "Clear sky"), so the words in an answer never come from the model's memory; and whether a
place's name may mean more than one place, so the model asks which one before it fetches any weather.
"""

from collections.abc import Sequence
from typing import Final

from nimbus.open_meteo import Place

# The codes and their words are WMO's, as Open-Meteo's documentation lists them (open-meteo.com/en/docs, "WMO Weather
# interpretation codes").
CONDITIONS: Final[dict[int, str]] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
UNKNOWN_CONDITIONS: Final = "Unknown conditions"
# A rival place makes a name ambiguous when the largest place has at most 3 times its population.
LARGEST_TO_RIVAL_MAX_RATIO: Final = 3


def to_condition(code: int | None) -> str:
    """A WMO weather code in words; a code that isn't in the table, or none, says so."""
    if code is None:
        return UNKNOWN_CONDITIONS
    return CONDITIONS.get(code, f"{UNKNOWN_CONDITIONS} (WMO code {code})")


def _is_elsewhere(place: Place, other: Place) -> bool:
    """Whether two places are in different regions: another first-level region (a state, say), or another country."""
    return place.region != other.region or place.country_code != other.country_code


def is_ambiguous_place(candidates: Sequence[Place]) -> bool:
    """
    Whether a name may mean more than one place: true when the largest place elsewhere has at least a third of the
    largest place's population, or when the largest place's population isn't known and there's a place elsewhere.
    Open-Meteo sorts its places by relevance, so this sorts them by population first.
    """
    ranked = sorted(candidates, key=lambda place: -1 if place.population is None else place.population, reverse=True)
    if not ranked:
        return False
    largest, *others = ranked
    rival = next((other for other in others if _is_elsewhere(largest, other)), None)
    if rival is None:
        return False
    if largest.population is None:
        return True
    return largest.population <= (rival.population or 0) * LARGEST_TO_RIVAL_MAX_RATIO
