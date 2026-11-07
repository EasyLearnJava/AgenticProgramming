"""A clear weather-only date beyond the local forecast window never needs a model or geocoder."""

from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nimbus.forecast_horizon import forecast_limit_reply

NOW = datetime(2026, 11, 7, 1, tzinfo=UTC)


def test_far_future_golden_skips_every_tool_and_the_model(client: TestClient) -> None:
    """Reproduce the production London question without supplying a model or receiving any tool chip."""
    app = cast(FastAPI, client.app)
    app.state.chat_model = None
    response = client.post("/api/chat", data={"question": "What will the weather be in London 30 days from now?"})
    assert response.status_code == 200
    assert "16 days" in response.text
    assert 'class="tool-chip-name"' not in response.text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Forecast for Dallas in 16 days?", True),
        ("Forecast for Dallas in 15 days?", False),
        ("In 4 weeks, will it rain in London?", True),
        ("What will the weather be in Dallas, TX on 2026-11-22?", True),
        ("What will the weather be in Dallas on 2026-11-21?", False),
        ("Weather in Athens for the next 30 days?", False),
        ("Give me hotels and the forecast in London in 30 days", False),
        ("Forecast for London and find hotels in 30 days", False),
        ("What will the weather be in London in 30 days? Find flights too.", False),
        ("What will the weather be in London tomorrow and in 30 days?", False),
        ("What will the weather be in London today or in 30 days?", False),
        ("What will the weather be in London on 2026-02-30?", False),
        ("What was the weather in London 30 days ago?", False),
    ],
)
def test_only_a_single_far_future_weather_date_is_intercepted(text: str, expected: bool) -> None:
    """A thirty-day duration, a second task, and a second date all remain the agent's responsibility."""
    result = forecast_limit_reply(text, NOW, "America/Chicago")
    assert (result is not None) is expected
    if result is not None:
        assert "November 21" in result


def test_date_boundary_uses_the_visitors_local_calendar() -> None:
    """November 22 lies within the forecast window for the same instant in Tokyo."""
    assert forecast_limit_reply("Forecast for Dallas on 2026-11-22?", NOW, "Asia/Tokyo") is None
