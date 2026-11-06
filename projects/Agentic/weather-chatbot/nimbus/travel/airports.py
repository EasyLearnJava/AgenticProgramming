"""Offline airport clocks. Only IATA identifiers paired with an IANA zone enter this lookup."""

import json
from pathlib import Path
from typing import Final

# Derived from the pinned airportsdata CSV; see the license and version beside the snapshot.
_DATA = Path(__file__).resolve().parents[2] / "data" / "travel" / "airport-zones.json"
AIRPORT_ZONES: Final[dict[str, str]] = {
    airport: zone for zone, codes in json.loads(_DATA.read_text(encoding="utf-8")).items() for airport in codes.split()
}

# A short city name can also be an unrelated airport code. Unfamiliar codes must be explicit (uppercase).
_LOWERCASE_AIRPORTS: Final = frozenset(
    [
        "atl",
        "aus",
        "bos",
        "bwi",
        "clt",
        "dal",
        "dca",
        "den",
        "dfw",
        "dtw",
        "ewr",
        "fat",
        "hou",
        "iad",
        "iah",
        "jfk",
        "las",
        "lax",
        "lga",
        "mco",
        "mdw",
        "mia",
        "msp",
        "ord",
        "pdx",
        "phl",
        "phx",
        "san",
        "sea",
        "sfo",
        "sgu",
        "sjc",
        "slc",
    ]
)


def normalize_origin(value: str) -> str:
    """Normalize familiar lowercase IATA identifiers; preserve a city or an explicit uppercase code."""
    return value.upper() if value in _LOWERCASE_AIRPORTS else value
