"""Explicit memory requests become an editable whitelist preview, never an automatic conversation upload."""

import re
from dataclasses import dataclass
from typing import Literal

from nimbus.memory.models import PreferenceProfile

type MemoryCommand = Literal["preview", "manage", "forget"]


@dataclass(frozen=True)
class MemoryIntent:
    """An explicit management request; the eventual form submit remains the write authorization."""

    kind: MemoryCommand
    preferences: PreferenceProfile
    message: str


def memory_intent(question: str, preferences: PreferenceProfile) -> MemoryIntent | None:
    """Recognize narrow user commands and display only supported normalized preference fields."""
    text = question.strip().rstrip(".?!").lower().replace("\u2019", "'")
    if re.fullmatch(r"(?:please )?forget (?:all )?my (?:saved |travel )?(?:preferences|memories)", text):
        return MemoryIntent(
            "forget", preferences, "Review and confirm deletion on My preferences. Nothing is deleted yet."
        )
    if re.fullmatch(r"(?:what do you remember(?: about me)?|show (?:me )?my (?:saved |travel )?preferences)", text):
        return MemoryIntent(
            "manage", preferences, "Manage the preferences connected to this browser on My preferences."
        )
    if not re.match(r"^(?:please )?(?:remember\b|save (?:my |these )?(?:travel )?preferences\b)", text):
        return None
    fields = preferences.model_dump()
    # ① Preview only whitelisted stable facts. Ambiguous or negative clauses are left for the editable form.
    if not re.search(r"\b(?:no|not|never|don't|do not|forget|except|avoid|without)\b", text):
        origins = set(re.findall(r"\b(?:from|airport (?:is|as))\s+([a-z]{3})\b", text)) - {"the", "any", "our"}
        alternatives = re.findall(r"\bfrom\s+[a-z]{3}\s+(?:or|and)\s+([a-z]{3})\b", text)
        origins.update(alternatives)
        if len(origins) == 1:
            fields["origin"] = origins.pop().upper()
        metric = bool(re.search(r"\b(?:celsius|metric)\b|°c\b", text))
        imperial = bool(re.search(r"\b(?:fahrenheit|imperial)\b|°f\b", text))
        if metric != imperial:
            fields["unit_system"] = "metric" if metric else "imperial"
        currencies = set(re.findall(r"\b(?:usd|eur|gbp|cad)\b", text))
        if len(currencies) == 1:
            fields["currency"] = currencies.pop().upper()
        activities = [name for name in ("easy hikes", "sightseeing", "camping") if name in text]
        if len(activities) == 1:
            fields["activity"] = activities[0]
        elif not activities and re.search(r"\bhiking\b", text):
            fields["activity"] = "hiking"
        windows = set(re.findall(r"\b(?:morning|evening)\b", text))
        if len(windows) == 1 and re.search(
            r"\b(?:depart|departure|departures|leave|leaving|fly|flight|flights)\b", text
        ):
            fields["depart_window"] = windows.pop()
    # ② The exact fields are shown for approval; any unsupported information is explicitly excluded.
    return MemoryIntent(
        "preview",
        PreferenceProfile.model_validate(fields),
        "Review the fields below. Only these preferences will be saved, after you choose Save preferences.",
    )
