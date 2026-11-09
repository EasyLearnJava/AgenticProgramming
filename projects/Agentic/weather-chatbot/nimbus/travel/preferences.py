"""Apply approved travel preferences as editable defaults before interpreting a park trip's local dates."""

from collections.abc import Mapping
from datetime import datetime

from nimbus.memory.models import PreferenceProfile
from nimbus.park_tools import KnowledgeService
from nimbus.travel.planner_intake import TripIntent, analyze_trip


def prefill_preferences(fields: Mapping[str, str], preferences: PreferenceProfile) -> dict[str, str]:
    """Prefill an initial form, preserving explicit values including an intentionally empty choice."""
    defaults = {name: str(value) for name, value in preferences.model_dump().items() if value}
    return {**defaults, **fields}


def analyze_with_preferences(
    question: str,
    knowledge: KnowledgeService | None,
    previous_user_text: str,
    now: datetime,
    time_zone: str,
    preferences: PreferenceProfile,
) -> TripIntent | None:
    """Use the normal intent resolver with typed defaults, without turning memories into user instructions."""
    return analyze_trip(
        question, knowledge, previous_user_text, now, time_zone, defaults=prefill_preferences({}, preferences)
    )
