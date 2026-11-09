"""The explicit preference vocabulary and sanitized outcomes shared by memory UI, chat and planning."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

type UnitSystem = Literal["", "metric", "imperial"]
type PreferenceCurrency = Literal["", "USD", "EUR", "GBP", "CAD"]
type ActivityPreference = Literal["", "easy hikes", "hiking", "sightseeing", "camping"]
type DeparturePreference = Literal["", "morning", "evening", "by_noon"]
type MemoryStatus = Literal["ready", "empty", "unavailable", "conflict", "pending"]
type MemoryReason = Literal[
    "",
    "not_configured",
    "invalid_identity",
    "timeout",
    "authentication_failed",
    "rate_limited",
    "unavailable",
    "invalid_response",
    "pagination_limit",
    "ownership_mismatch",
    "stale_revision",
    "duplicates",
    "pending_confirmation",
]


class PreferenceProfile(BaseModel):
    """Only explicitly approved stable defaults; no raw conversation, dates, prices or safety judgments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: Annotated[str, StringConstraints(pattern=r"^(?:[A-Z]{3})?$")] = ""
    unit_system: UnitSystem = ""
    currency: PreferenceCurrency = ""
    activity: ActivityPreference = ""
    depart_window: DeparturePreference = ""

    @field_validator("origin", mode="before")
    @classmethod
    def normalize_origin(cls, value: object) -> object:
        """Accept an airport code case-insensitively without interpreting free-form instructions."""
        return value.strip().upper() if isinstance(value, str) else value


class Snapshot(BaseModel):
    """A complete read or verified write result; unavailable and conflicting data are never usable defaults."""

    model_config = ConfigDict(frozen=True)

    status: MemoryStatus
    preferences: PreferenceProfile = Field(default_factory=PreferenceProfile)
    revision: str = ""
    reason: MemoryReason = ""
    memory_ids: tuple[str, ...] = ()
