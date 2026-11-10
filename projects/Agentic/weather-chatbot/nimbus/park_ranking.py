"""Pure season interpretation and rank fusion shared by local and hosted park retrieval."""

import re
from datetime import date
from typing import Literal

type VisitSeason = Literal["winter", "spring", "summer", "fall"]
type SeasonSource = Literal["date", "explicit", "query", "none"]
RRF_K = 60
SEMANTIC_WEIGHT = 0.1
SEASONS: tuple[VisitSeason, ...] = ("winter", "spring", "summer", "fall")
_SEASON = r"(spring|summer|fall|autumn|winter)"


def resolve_season(
    query: str, visit_date: date | None, explicit: VisitSeason | None
) -> tuple[VisitSeason | None, SeasonSource]:
    """Honor actual dates/explicit selections; infer only one contextual season without fabricating a date."""
    if explicit is not None and explicit not in SEASONS:
        raise ValueError("Unsupported visit season")
    if visit_date is not None:
        season = SEASONS[(visit_date.month % 12) // 3]
        if explicit is not None and explicit != season:
            raise ValueError("Visit date and season disagree")
        return season, "date"
    if explicit is not None:
        return explicit, "explicit"
    # Place names and fall-protection equipment are not seasonal instructions.
    text = re.sub(r"\b(?:big spring|nevada fall|vernal fall|fall[- ]protection)\b", "", query.casefold())
    words = {"fall" if word == "autumn" else word for word in re.findall(rf"\b{_SEASON}\b", text)}
    contextual = re.search(
        rf"\b(?:in|during|for|this|next|early|late)\s+(?:the\s+)?{_SEASON}\b|"
        rf"\b{_SEASON}\s+(?:clothing|weather|hiking|hike|gear|equipment|preparation|packing|trip|visit)\b",
        text,
    )
    if len(words) == 1 and contextual:
        return next(season for season in SEASONS if season in words), "query"
    return None, "none"


def reciprocal_ranks(scores: dict[str, float], *, minimum: float, positive: bool = False) -> dict[str, int]:
    """Rank qualifying matches once, using chunk IDs for deterministic ties and never zero-score padding."""
    included = [identity for identity, score in scores.items() if score >= minimum and (not positive or score > 0)]
    return {identity: rank for rank, identity in enumerate(sorted(included, key=lambda key: (-scores[key], key)), 1)}
