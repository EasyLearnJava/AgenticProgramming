"""Versioned, bounded cache records: Markdown and validated weather evidence, never executable HTML."""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from nimbus.request_trace import CacheRejection
from nimbus.tools import CurrentWeatherOutput, ForecastOutput, GeocodeOutput

MODEL = "sentence-transformers/all-minilm-l6-v2"
VERSION: Final = "weather-answer-v1"
TTL_SECONDS = 120


class CachePolicy(BaseModel):
    """Independent dimensions that similarity is never allowed to override."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    place: str = Field(min_length=2, max_length=80)
    intent: Literal["overview", "today", "current"]
    units: Literal["metric", "imperial"]
    locale: str = Field(max_length=35)
    time_zone: str = Field(max_length=100)
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class WeatherEvidence(BaseModel):
    """A single unambiguous destination and complete successful weather outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    places: GeocodeOutput
    current: CurrentWeatherOutput
    forecast: ForecastOutput | None = None


class CacheEntry(BaseModel):
    """A private, integrity-protected answer with an absolute, non-sliding lifetime."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    version: Literal["weather-answer-v1"] = VERSION
    scope: str = Field(pattern=r"^[a-f0-9]{64}$")
    context: str = Field(pattern=r"^[a-f0-9]{64}$")
    exact: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy: CachePolicy
    label: str = Field(min_length=1, max_length=160)
    answer: str = Field(min_length=1, max_length=12000)
    evidence: WeatherEvidence
    created_at: float
    expires_at: float
    evidence_fetched_at: float


class CacheListing(BaseModel):
    """A bounded private listing, distinguishing an empty cache from an unavailable one."""

    status: Literal["ready", "unavailable", "disabled"]
    entries: tuple[CacheEntry, ...] = ()


class CacheLookup(BaseModel):
    """Only an on-mode hit may bypass Gemini; shadow hits remain measurements."""

    status: Literal["exact_hit", "semantic_hit", "miss", "error", "shadow_hit", "bypass"]
    entry: CacheEntry | None = None


class CacheStore(BaseModel):
    """A cache write's actual outcome, separate from whether the weather answer itself succeeded."""

    # timed_out: the save was sent, then our deadline passed; Qdrant may still have applied it.
    status: Literal["saved", "not_reusable", "cache_full", "error", "bypass", "timed_out"]
    # not_reusable only: the evidence check that kept the answer out.
    reason: CacheRejection | None = None
