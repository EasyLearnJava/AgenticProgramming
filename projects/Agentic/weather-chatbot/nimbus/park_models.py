"""Typed public park records shared by ingestion, Qdrant validation and destination routing."""

from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from nimbus.utils import checked_source_url

type Identity = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,100}$")]
type Season = Literal["all", "winter", "spring", "summer", "fall"]


class Destination(BaseModel):
    """One supported destination and an explicitly labeled forecast reference point."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identity
    park_id: Identity
    name: str = Field(min_length=1, max_length=150)
    aliases: list[str] = Field(min_length=1, max_length=20)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    time_zone: str
    forecast_reference: str = Field(min_length=1, max_length=500)
    source_url: str

    _source = field_validator("source_url")(checked_source_url)

    @field_validator("time_zone")
    @classmethod
    def known_time_zone(cls, value: str) -> str:
        """A timezone that can be used for destination-local dates."""
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError("Unknown destination timezone") from error
        return value


class ParkChunk(BaseModel):
    """An attributed passage with explicit destination and seasonal applicability."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identity
    document_id: Identity
    park_id: Identity
    destination_ids: list[Identity] = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=300)
    section: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=8000)
    source_url: str
    source_updated_at: str | None = None
    fetched_at: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    seasons: list[Season] = Field(default_factory=lambda: list[Season](["all"]), min_length=1, max_length=4)

    _source = field_validator("source_url")(checked_source_url)

    @field_validator("source_updated_at")
    @classmethod
    def source_date(cls, value: str | None) -> str | None:
        """An actual source date when the publisher exposes one; never the fetch date substituted for it."""
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator("fetched_at")
    @classmethod
    def fetched_timestamp(cls, value: str) -> str:
        """An ingestion timestamp with its timezone."""
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("Ingestion time needs a timezone")
        return value
