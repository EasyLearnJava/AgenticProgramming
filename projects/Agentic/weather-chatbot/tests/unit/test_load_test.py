"""
tests/unit/test_load_test.py: the load test (step 13): the nearest-rank percentile; each kind's summary, its failures
counted; a request that can't be made, a failure with its time; and a small load against the app in this process,
where a question works only when its answer ended well.
"""

import asyncio

import httpx2
import pytest

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from tests.fakes import PARIS_STEPS, FakeCacheStore, FakeModel, OpenMeteoRecordings
from tools.load_test import Timed, percentile, run_load, timed, to_summary


@pytest.mark.parametrize(
    ("seconds", "share", "expected"), [([0.4], 0.95, 0.4), ([4, 1, 3, 2], 0.5, 2), (list(range(1, 21)), 0.95, 19)]
)
def test_a_percentile_is_the_nearest_rank(seconds: list[float], share: float, expected: float) -> None:
    assert percentile(seconds, share) == expected


def test_each_kind_says_how_many_how_many_failed_and_its_times() -> None:
    results = [Timed("page", True, 0.2), Timed("page", False, 0.4), Timed("question", True, 3.0)]
    assert to_summary(results) == [
        "page       2 sent, 1 failed · p50 0.20 s, p95 0.40 s, slowest 0.40 s",
        "question   1 sent, 0 failed · p50 3.00 s, p95 3.00 s, slowest 3.00 s",
    ]


def test_a_request_that_can_t_be_made_is_a_failure_with_its_time() -> None:
    async def unreachable() -> bool:
        raise httpx2.ConnectError("no route to host")

    result = asyncio.run(timed("health", unreachable))
    assert (result.kind, result.ok) == ("health", False)
    assert result.seconds >= 0


@pytest.mark.parametrize("answers", [True, False])
def test_a_small_load_against_the_app_in_this_process(
    settings: Settings, open_meteo: OpenMeteoRecordings, answers: bool
) -> None:
    model = FakeModel(tool_steps=PARIS_STEPS) if answers else FakeModel(fail_after_first_word=RuntimeError("quota"))
    app = create_app(settings)
    app.state.chat_model = model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())
    # Our MCP server, in this process, by a local name, which its Host check allows (issue 62).
    app.state.to_mcp_url = lambda _request, _settings: "http://127.0.0.1:8000/api/mcp"
    app.state.make_mcp_http_client = lambda: httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app))

    async def go() -> list[Timed]:
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as http,
        ):
            return await run_load(http, "http://testserver", pages=2, questions=1, at_once=2)

    results = asyncio.run(go())
    assert sorted(result.kind for result in results) == ["health", "health", "page", "page", "question"]
    assert all(result.ok for result in results if result.kind != "question")
    assert [result.ok for result in results if result.kind == "question"] == [answers]
