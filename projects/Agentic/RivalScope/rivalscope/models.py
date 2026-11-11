"""Domain records persisted as plain JSON-compatible values by the workflow."""

import re
from datetime import date
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

FieldName = Literal["pricing", "features", "positioning", "news"]
FIELDS: tuple[FieldName, ...] = ("pricing", "features", "positioning", "news")
LABELS = {
    "pricing": "Pricing",
    "features": "Core features",
    "positioning": "Market positioning",
    "news": "Recent news",
}
NEWS_DAYS = 90


def one_line(value: str) -> str:
    return " ".join(value.split()) if isinstance(value, str) else value


def website_domain(value: str) -> str:
    """Accept an optional hostname or HTTP(S) website and return its public name."""
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").rstrip(".").removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("Enter a public website, such as asana.com.")
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z][a-z0-9-]*", host):
        raise ValueError("Enter a public website, such as asana.com.")
    if host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("Enter a public website.")
    return host


def public_url(value: str) -> str:
    """Keep citation links safe to display. The app never requests these URLs directly."""
    try:
        parsed = urlsplit(value)
        if not website_domain(value):
            return ""
        port = parsed.port
        if not parsed.netloc or parsed.scheme not in {"https", "http"} or port not in {None, 80, 443}:
            return ""
        if any(ch.isspace() or ch in '<>"\\' or ord(ch) < 32 for ch in value):
            return ""
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
    except (TypeError, ValueError):
        return ""


class Record(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Company(Record):
    name: str = Field(min_length=2, max_length=100)
    website: str = Field(default="", max_length=250)
    scope: str = Field(default="", max_length=240)

    _normalize_text = field_validator("name", "scope", mode="before")(one_line)
    _normalize_domain = field_validator("website")(website_domain)


class Candidate(Record):
    name: str = Field(min_length=2, max_length=100)
    website: str = Field(default="", max_length=250)
    reason: str = Field(default="", max_length=350)
    discovery_ids: list[str] = Field(default_factory=list, max_length=4)

    _normalize_text = field_validator("name", "reason", mode="before")(one_line)
    _normalize_domain = field_validator("website")(website_domain)


def review_candidates(rows: list[dict], company: Company) -> list[Candidate]:
    candidates = [Candidate.model_validate(row) for row in rows]
    names = [item.name.casefold() for item in candidates]
    domains = [item.website for item in candidates if item.website]
    if len(names) != 3 or len(set(names)) != 3 or len(set(domains)) != len(domains):
        raise ValueError("Enter three distinct competitors and avoid duplicate websites.")
    if company.name.casefold() in names or (company.website and company.website in domains):
        raise ValueError("The company being researched cannot also be a competitor.")
    return candidates


class Source(Record):
    id: str
    url: str
    title: str
    excerpt: str
    field: FieldName | Literal["discovery"]
    retrieved: date
    published: date | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if url := public_url(value):
            return url
        raise ValueError("Unsupported source URL.")


class Finding(Record):
    field: FieldName
    text: str = Field(min_length=3, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=3)
    quote: str = Field(default="", max_length=600)

    _normalize_text = field_validator("text", mode="before")(one_line)


class Profile(Record):
    competitor: Candidate
    sources: list[Source] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def gaps(self) -> list[FieldName]:
        covered = {finding.field for finding in self.findings}
        return [field for field in FIELDS if field not in covered]


class BriefingSummary(Record):
    competitors: int
    covered_fields: int
    total_fields: int
    cited_pages: int

    @classmethod
    def from_profiles(cls, profiles: list[Profile]) -> "BriefingSummary":
        cited_pages = set()
        for profile in profiles:
            cited_ids = {key for finding in profile.findings for key in finding.source_ids}
            cited_pages.update(source.url for source in profile.sources if source.id in cited_ids)
        return cls(
            competitors=len(profiles),
            covered_fields=sum(len(FIELDS) - len(profile.gaps) for profile in profiles),
            total_fields=len(profiles) * len(FIELDS),
            cited_pages=len(cited_pages),
        )
