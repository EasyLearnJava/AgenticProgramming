"""
nimbus/prompts.py: what the model is told before each question: who it is, its rules, the units for the visitor's
locale, and the visitor's own time and days. Step 3's model has no tools, so its first rule is to give no weather as
fact; step 4 gives it the weather tools.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from nimbus.constants import IMPERIAL_REGIONS
from nimbus.utils import to_iso

RULES = """You are Nimbus, a weather assistant in a chat.

Rules:
1. You can't look up the weather yet: live weather and forecasts come in a later version of this chat. Never give a
temperature, a forecast or current conditions for any place or day as fact; say instead that you can't check the
weather yet.
2. You can explain weather in general: what a forecast term means, how a kind of weather forms, or what to wear for
weather the user describes.
3. Answer only about the weather. For anything else, say in one polite sentence what you can do.
4. Keep answers short: two to four sentences, in plain words, without tables.
5. Use {units} unless the user asks for others; then keep their choice for the rest of the chat."""

IMPERIAL = "imperial units (°F, mph, inches)"
METRIC = "metric units (°C, km/h, mm)"
DAY = "%A %Y-%m-%d"


def to_region(locale: str) -> str:
    """
    A language tag's region: its subtag of two letters or three digits ("en-US" → "US", "zh-Hant-TW" → "TW", "es-419"
    → "419"), before any extension or private part (-u-..., -x-...); "" when it has none.
    """
    for subtag in locale.split("-")[1:]:
        if len(subtag) == 1:
            break
        if (len(subtag) == 2 and subtag.isalpha()) or (len(subtag) == 3 and subtag.isdigit()):
            return subtag.upper()
    return ""


def to_units(locale: str) -> str:
    """The units for a locale: imperial where its region uses them (en-US), else metric (en-GB, fr, ...)."""
    return IMPERIAL if to_region(locale) in IMPERIAL_REGIONS else METRIC


def to_system_prompt(now: datetime, locale: str, time_zone: str) -> str:
    """
    The system prompt for one question: the rules, the units for the visitor's locale, and the visitor's own time,
    today and tomorrow, from their time zone, so "tomorrow" means their tomorrow.
    """
    # ① The rules, with the units.
    rules = RULES.format(units=to_units(locale))
    # ② The time, in UTC and in the visitor's own zone.
    local = now.astimezone(ZoneInfo(time_zone))
    tomorrow = local + timedelta(days=1)
    context = (
        f"The time now is {to_iso(now.astimezone(UTC))} (UTC). The user's browser locale is {locale}.\n"
        f"The user's own time now is {local.strftime(DAY)} {local:%H:%M} ({time_zone}): today is "
        f"{local.strftime(DAY)}, tomorrow is {tomorrow.strftime(DAY)}."
    )
    return f"{rules}\n\n{context}"


def to_messages(question: str, now: datetime, locale: str, time_zone: str) -> list[BaseMessage]:
    """What the model gets for one question: the system prompt, then the question."""
    return [SystemMessage(to_system_prompt(now, locale, time_zone)), HumanMessage(question)]
