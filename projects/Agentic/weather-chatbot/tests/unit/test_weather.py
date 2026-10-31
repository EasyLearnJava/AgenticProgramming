"""
tests/unit/test_weather.py: what the tools decide in code: the words for a weather code, and whether a place's name
may mean more than one place, on Open-Meteo's recorded answers for six names.
"""

import pytest

from nimbus.open_meteo import Place
from nimbus.weather import is_ambiguous_place, to_condition
from tests.fakes import open_meteo_answer


@pytest.mark.parametrize(
    ("code", "words"),
    [
        (0, "Clear sky"),
        (2, "Partly cloudy"),
        (45, "Fog"),
        (63, "Moderate rain"),
        (99, "Thunderstorm with heavy hail"),
        (42, "Unknown conditions (WMO code 42)"),
        (None, "Unknown conditions"),
    ],
)
def test_a_weather_code_is_wmo_s_words(code: int | None, words: str) -> None:
    assert to_condition(code) == words


def places(name: str) -> list[Place]:
    """The places Open-Meteo's geocoding found for a name, recorded."""
    return [Place.model_validate(result) for result in open_meteo_answer(f"geocode-{name}").get("results", [])]


@pytest.mark.parametrize(
    ("name", "ambiguous"),
    [
        # Paris, France (2,138,551) dwarfs Paris, Texas (24,782).
        ("paris", False),
        # Missouri (170,188) and Massachusetts (154,341): neither is three times the other.
        ("springfield", True),
        # A region after a comma narrows the search: all five are in Massachusetts.
        ("springfield-ma", False),
        # Three places, none with a population: the largest isn't known.
        ("narnia", True),
        # A real town in South Africa (82,736), and a Florida one of 2,106.
        ("atlantis", False),
        # No places at all: nothing to ask.
        ("hogwarts", False),
    ],
)
def test_a_name_is_ambiguous_when_a_place_elsewhere_has_a_third_of_the_largest_one_s_people(
    name: str, ambiguous: bool
) -> None:
    assert is_ambiguous_place(places(name)) is ambiguous


def test_the_largest_place_is_found_by_population_not_by_open_meteo_s_order() -> None:
    small = Place(name="A", region="One", country_code="US", latitude=0, longitude=0, population=1_000)
    large = Place(name="A", region="Two", country_code="US", latitude=0, longitude=0, population=1_000_000)
    assert is_ambiguous_place([small, large]) is False
