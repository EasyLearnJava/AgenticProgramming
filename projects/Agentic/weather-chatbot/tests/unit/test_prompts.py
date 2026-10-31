"""
tests/unit/test_prompts.py: the system prompt: the rules, the units for the visitor's locale, and the visitor's own
time, today and tomorrow, from their time zone; then the question, as the model gets them.
"""

from datetime import UTC, datetime

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from nimbus.prompts import IMPERIAL, METRIC, to_messages, to_system_prompt, to_units

NOW = datetime(2026, 10, 31, 3, 30, tzinfo=UTC)


def test_says_it_can_t_check_the_weather_yet_and_answers_only_about_the_weather() -> None:
    prompt = to_system_prompt(NOW, "en-US", "UTC")
    assert prompt.startswith("You are Nimbus, a weather assistant in a chat.")
    assert "You can't look up the weather yet" in prompt
    assert "Answer only about the weather." in prompt


@pytest.mark.parametrize(
    ("locale", "units"),
    [
        ("en-US", IMPERIAL),
        ("es-US", IMPERIAL),
        ("en-LR", IMPERIAL),
        ("en-GB", METRIC),
        ("fr", METRIC),
        ("de-DE", METRIC),
        ("en-US-posix", IMPERIAL),
        ("en-US-u-hc-h23", IMPERIAL),
        ("zh-Hant-TW", METRIC),
        ("es-419", METRIC),
        ("en-x-us", METRIC),
    ],
)
def test_the_units_follow_the_locale_s_region(locale: str, units: str) -> None:
    assert to_units(locale) == units
    assert units in to_system_prompt(NOW, locale, "UTC")


def test_today_and_tomorrow_are_the_visitor_s_own() -> None:
    # 03:30 in UTC on Saturday is still Friday evening in Chicago.
    prompt = to_system_prompt(NOW, "en-US", "America/Chicago")
    assert "The time now is 2026-10-31T03:30:00.000Z (UTC)." in prompt
    assert "The user's own time now is Friday 2026-10-30 22:30 (America/Chicago)" in prompt
    assert "today is Friday 2026-10-30, tomorrow is Saturday 2026-10-31." in prompt


def test_the_model_gets_the_system_prompt_then_the_question() -> None:
    system, question = to_messages("Is it windy?", NOW, "en-GB", "Europe/London")
    assert isinstance(system, SystemMessage)
    assert "(Europe/London)" in str(system.content)
    assert isinstance(question, HumanMessage)
    assert question.content == "Is it windy?"
