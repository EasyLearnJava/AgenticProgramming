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
_MONTH = r"(?:january|february|march|april|june|july|august|september|october|november|december)"
# "May" is the month only beside a word such as "in" or a day ("in May", "May 12"); "layers I may need" is the verb.
_MAY = r"\b(?:in|during|this|next|early|late|mid|of)\s+may\b|\bmay\s+\d"
_SEASON_WORDS = r"\b(?:in|during|for|this|next|early|late)\s+(?:the\s+)?"


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
    # A month says when the visit is, so a season word beside it ("winter gear for July") is not a filter.
    if re.search(rf"\b{_MONTH}\b|{_MAY}", text):
        return None, "none"
    # "Fall" is surely the season only after a word such as "in" or "late"; anywhere else it may be the verb or a
    # waterfall ("a fall hiking", "Yosemite Fall", "summer and fall"), so the question gets no season from its words:
    # dropping passages on a guess is the harm to avoid.
    for found in re.finditer(r"\bfall\b(?!-\w)", text):
        if not re.search(rf"{_SEASON_WORDS}$", text[: found.start()]):
            return None, "none"
    # A season joined to a word ("spring-fed") is no season, so it never cancels one ("spring-fed pools in summer").
    words = {"fall" if word == "autumn" else word for word in re.findall(rf"\b{_SEASON}\b(?!-\w)", text)}
    contextual = re.search(
        rf"{_SEASON_WORDS}{_SEASON}(?![-\w])|"
        rf"\b{_SEASON}(?![-\w])\s+(?:clothing|weather|hiking|hike|gear|equipment|preparation|packing|trip|visit)\b",
        text,
    )
    if len(words) == 1 and contextual:
        return next(season for season in SEASONS if season in words), "query"
    return None, "none"


def reciprocal_ranks(scores: dict[str, float], *, minimum: float, positive: bool = False) -> dict[str, int]:
    """Rank qualifying matches once, using chunk IDs for deterministic ties and never zero-score padding."""
    included = [identity for identity, score in scores.items() if score >= minimum and (not positive or score > 0)]
    return {identity: rank for rank, identity in enumerate(sorted(included, key=lambda key: (-scores[key], key)), 1)}
