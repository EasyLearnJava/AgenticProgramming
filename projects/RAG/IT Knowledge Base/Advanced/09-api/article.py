"""
IT Knowledge Base: An Article, Checked
======================================

The data contract every article must meet before it becomes a Document, and the rules that make its labels reliable
enough to filter by. It handles:
  1. Article: one article as a Pydantic model: the required fields, the most characters each may have, a priority
     from four values, the tags as a list, and who may see it (visibility, team)
  2. Spellings: one spelling for each value of a label, from a table in kb_settings.toml
  3. doc_id(): an ID that stays the same when the file is re-sorted: the export's own id, or a hash of named fields

    Article.model_validate({"title": "VPN Connection Timeout", ..., "priority": "High", "tags": "vpn; VPN;remote"})
      ->  Article(title="VPN Connection Timeout", ..., priority=Priority.HIGH, tags=["vpn", "remote"])
"""
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from utils import short_hash, simplify, spelling_key

# A value given in a validation error is shown up to this many characters; a longer one isn't shown
SHOW_GIVEN_LIMIT = 40


class Priority(StrEnum):
    """How urgent an article's problem is: one of four values, so "priority is High" filters exactly."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


# Who may see an article: anyone, staff only, or only its team
Visibility = Literal["public", "internal", "restricted"]


# -------------------------------------------------
# Article - The Data Contract
# -------------------------------------------------

class Article(BaseModel):
    """One knowledge base article, checked: a value that breaks a rule fails validation, naming the field and why."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    id: str | None = Field(default=None, max_length=100)        # the article's key in the source system, if any
    title: str = Field(min_length=1, max_length=200)
    problem: str = Field(min_length=1, max_length=5_000)
    resolution: str = Field(min_length=1, max_length=10_000)
    notes: str | None = Field(default=None, max_length=5_000)
    system: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    priority: Priority | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    visibility: Visibility | None = None                        # None: the export doesn't say
    team: str | None = Field(default=None, max_length=100)

    @field_validator("id", "notes", "system", "category", "priority", "visibility", "team", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        """An empty optional value means "not given", not a label that's an empty string."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("visibility", mode="before")
    @classmethod
    def _visibility_in_lower_case(cls, value):
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("tags", mode="before")
    @classmethod
    def _split_tags(cls, value):
        """"vpn; VPN;remote;" -> ["vpn", "remote"]: split on ";", lower case, spaces trimmed, each once, no blanks."""
        if not isinstance(value, str):
            return value
        tags: list[str] = []
        for tag in value.split(";"):
            tag = simplify(tag)
            if tag and tag not in tags:
                tags.append(tag)
        return tags


# Every field an article can have, in order; the ones it must have
ARTICLE_FIELDS = tuple(Article.model_fields)
REQUIRED_FIELDS = tuple(name for name, info in Article.model_fields.items() if info.is_required())


def describe(error: ValidationError) -> str:
    """A validation error as one line: each field that failed, why, and the value given (if it's short)."""
    parts = []
    for item in error.errors():
        name = ".".join(str(part) for part in item["loc"])
        message = item["msg"].removeprefix("Value error, ")      # a rule of the model's own: its message as written
        given = item.get("input")
        shown = f' (given "{given}")' if isinstance(given, str) and len(given) <= SHOW_GIVEN_LIMIT else ""
        parts.append(f"{name}: {message}{shown}" if name else message)
    return "; ".join(parts)


# -------------------------------------------------
# Spellings - One Spelling for Each Value of a Label
# -------------------------------------------------

class Spellings:
    """
    A label's table of spellings: each right spelling, and the other spellings that mean it. Upper and lower case,
    spaces, hyphens and underscores never count, so "Wi-Fi", "WIFI" and "wi fi" all find "WiFi" with no entry.
    """

    def __init__(self, table: Mapping[str, list[str]]):
        """
        Args:
            table: {right spelling: [other spellings]}, as kb_settings.toml's [spellings.<label>] holds it
        """
        self.table = dict(table)
        self._right_of = {spelling_key(spelling): right
                          for right, others in self.table.items() for spelling in (right, *others)}

    def right_spelling(self, value: str) -> str | None:
        """The right spelling of a value, or None when the table doesn't know it."""
        return self._right_of.get(spelling_key(value))


# -------------------------------------------------
# doc_id() - An ID That Survives Re-sorting the File
# -------------------------------------------------

def doc_id(values: Mapping[str, object], id_fields: tuple[str, ...]) -> str | None:
    """
    An article's ID: the export's own id when there is one; else "kb-" and a hash of the id_fields' values, in
    lower case with single spaces, so neither re-sorting the file nor changing the fix changes it.

    Returns None when an id_field has no value: there's nothing to make an ID from.
    """
    if values.get("id"):
        return str(values["id"])
    parts = [values.get(name) for name in id_fields]
    if not all(parts):
        return None
    return "kb-" + short_hash("\x1f".join(simplify(str(part)) for part in parts))
