"""Exercise travel validation, shared limits, cancellation and the model-facing search tools without the network."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError
from structlog.testing import capture_logs

from nimbus.travel.models import FlightSearch, HotelSearch, TravelCallRecord, TravelOffer, TravelReport
from nimbus.travel.service import TravelService
from nimbus.travel.tools import make_travel_tools

DAY = date(2034, 5, 18)
ROUTE = FlightSearch(origin="AUS", destination="LAS", departure_date=DAY)
STAY = HotelSearch(destination="Springdale, Utah", check_in=DAY, check_out=DAY + timedelta(days=3))


def _flight_result() -> TravelReport:
    """A synthetic quote with a private itinerary link that must never reach logs."""
    return TravelReport(
        provider="kiwi",
        status="found",
        offers=(TravelOffer(title="Example itinerary", url="https://www.kiwi.com/deep?offer=private-example"),),
    )


def test_parallel_duplicate_calls_share_one_budget_slot_and_one_record() -> None:
    """The planner and agent can start the same search simultaneously without paying for it twice."""

    async def check() -> None:
        calls = []

        async def flights(query: FlightSearch) -> TravelReport:
            calls.append(query)
            await asyncio.sleep(0)
            return _flight_result()

        turn = TravelService(flights=flights).new_turn(asyncio.get_running_loop().time() + 30, today=DAY)
        with capture_logs() as logs:
            results = await asyncio.gather(turn.search_flights(ROUTE), turn.search_flights(ROUTE))
            assert [result.status for result in results] == ["found", "found"]
            assert (await turn.search_flights(ROUTE.model_copy(update={"origin": "DFW"}))).status == "found"
            assert (await turn.search_flights(ROUTE.model_copy(update={"origin": "ORD"}))).status == "budget_exhausted"
        assert len(calls) == 2
        assert any(entry["deduplicated"] for entry in logs)
        logged = str(logs)
        for private in ("AUS", "Springdale", "2034", "private-example"):
            assert private not in logged

    asyncio.run(check())


def test_throttled_flights_do_not_call_again_and_hotel_still_returns() -> None:
    """An upstream refusal ends flight work for this turn only and preserves other service output."""

    async def check() -> None:
        calls = []

        async def flights(query: FlightSearch) -> TravelReport:
            calls.append(query)
            return TravelReport(provider="kiwi", status="rate_limited")

        async def hotels(query: HotelSearch) -> TravelReport:
            assert query == STAY
            return TravelReport(provider="trivago", status="no_results")

        service = TravelService(flights=flights, hotels=hotels)
        turn = service.new_turn(asyncio.get_running_loop().time() + 30, today=DAY)
        assert (await turn.search_flights(ROUTE)).status == "rate_limited"
        assert (await turn.search_flights(ROUTE.model_copy(update={"destination": "SGU"}))).status == "rate_limited"
        assert len(calls) == 1
        assert (await turn.search_hotels(STAY)).status == "no_results"

    asyncio.run(check())


@pytest.mark.parametrize(
    "change",
    [
        {"return_date": DAY - timedelta(days=1)},
        {"adults": 0},
        {"infants": 2},
        {"destination": "aus"},
        {"max_stops": -1},
        {"origin": "New\nYork"},
        {"unexpected": "value"},
        {"departure_date": 0},
        {"departure_date": "1924992000"},
        {"departure_date": "2034-05-18T00:00:00"},
    ],
)
def test_invalid_flight_search_is_rejected(change: dict[str, Any]) -> None:
    """Invalid dates, occupancy, extra fields and same-place route searches fail at the boundary."""
    with pytest.raises(ValidationError):
        FlightSearch.model_validate(ROUTE.model_dump() | change)


@pytest.mark.parametrize(
    "change",
    [
        {"check_out": DAY},
        {"rooms": 2, "adults": 1},
        {"children_ages": [18]},
        {"destination": None},
        {"latitude": 10},
        {"latitude": 20, "longitude": 500},
        {"latitude": 10, "longitude": 20},
    ],
)
def test_invalid_hotel_search_is_rejected(change: dict[str, Any]) -> None:
    """Hotel coordinates, occupancy and date interval must describe one real search."""
    with pytest.raises(ValidationError):
        HotelSearch.model_validate(STAY.model_dump() | change)


def test_cancelled_search_releases_slot_and_does_not_leave_detached_work() -> None:
    """Cancellation runs adapter cleanup and lets another turn use the same instance slot."""

    async def check() -> None:
        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def flights(query: FlightSearch) -> TravelReport:
            if query.origin == "AUS":
                try:
                    entered.set()
                    await asyncio.Future[None]()
                finally:
                    cleaned.set()
            return _flight_result()

        service = TravelService(flights=flights, concurrency=1)
        deadline = asyncio.get_running_loop().time() + 30
        turn = service.new_turn(deadline, today=DAY)
        pending = asyncio.create_task(turn.search_flights(ROUTE))
        await entered.wait()
        other = service.new_turn(deadline, today=DAY)
        alt = ROUTE.model_copy(update={"origin": "DEN"})
        assert (await other.search_flights(alt)).status == "busy"
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert cleaned.is_set()
        assert (await other.search_flights(ROUTE.model_copy(update={"origin": "MSP"}))).status == "found"

    asyncio.run(check())


def test_timeout_cancels_provider_and_tool_preserves_typed_artifact() -> None:
    """A stalled adapter ends inside the outer deadline and the renderer receives a safe failure artifact."""

    async def check() -> None:
        cleaned = asyncio.Event()

        async def flights(_: FlightSearch) -> TravelReport:
            try:
                await asyncio.Future[None]()
            finally:
                cleaned.set()
            return _flight_result()

        turn = TravelService(flights=flights, timeout=0.02).new_turn(asyncio.get_running_loop().time() + 30, today=DAY)
        tools = make_travel_tools(turn)
        assert [tool.name for tool in tools] == ["search_flights"]
        msg = await tools[0].ainvoke(
            {"type": "tool_call", "id": "flight-1", "name": "search_flights", "args": ROUTE.model_dump(mode="json")}
        )
        assert isinstance(msg, ToolMessage)
        assert isinstance(msg.artifact, TravelCallRecord)
        assert json.loads(str(msg.content))["status"] == msg.artifact.report.status == "timeout"
        assert cleaned.is_set()
        assert (await turn.search_hotels(STAY)).status == "disabled"

    asyncio.run(check())


def test_model_reads_offer_facts_but_only_verified_cards_receive_booking_links() -> None:
    """Both agent tools keep opaque, potentially identifying provider parameters out of the next model request."""

    async def check() -> None:
        flight_report = _flight_result()
        hotel_report = TravelReport(
            provider="trivago",
            status="found",
            offers=(TravelOffer(title="Example room", url="https://www.trivago.com/deal?session=private-example"),),
        )

        async def flights(_: FlightSearch) -> TravelReport:
            return flight_report

        async def hotels(_: HotelSearch) -> TravelReport:
            return hotel_report

        turn = TravelService(flights=flights, hotels=hotels).new_turn(asyncio.get_running_loop().time() + 30, today=DAY)
        cases = zip(make_travel_tools(turn), (ROUTE, STAY), (flight_report, hotel_report), strict=True)
        for tool, query, report in cases:
            assert report.offers[0].url
            message = await tool.ainvoke(
                {"type": "tool_call", "id": "travel-1", "name": tool.name, "args": query.model_dump(mode="json")}
            )
            assert isinstance(message, ToolMessage)
            assert isinstance(message.artifact, TravelCallRecord)
            assert message.artifact.sources == (report.offers[0].url,)
            assert json.loads(str(message.content))["offers"][0]["title"] == report.offers[0].title
            assert "private-example" not in str(message.content)
            assert "url" not in json.loads(str(message.content))["offers"][0]

    asyncio.run(check())


def test_past_search_or_expired_answer_makes_no_network_call() -> None:
    """Never contact a provider for a past date or when the answer's own time is exhausted."""

    async def check() -> None:
        calls = []

        async def flights(query: FlightSearch) -> TravelReport:
            calls.append(query)
            return _flight_result()

        service = TravelService(flights=flights)
        now = asyncio.get_running_loop().time()
        assert (await service.new_turn(now - 1, today=DAY).search_flights(ROUTE)).status == "timeout"
        assert (
            await service.new_turn(now + 30, today=DAY + timedelta(days=1)).search_flights(ROUTE)
        ).status == "invalid_input"
        assert not calls

    asyncio.run(check())


def test_unavailable_and_unusable_provider_outputs_are_explicit() -> None:
    """Provider bugs and schema drift do not look like an empty set of offers or leak provider messages."""

    async def check() -> None:
        async def flights(_: FlightSearch) -> TravelReport:
            raise OSError("private travel information")

        async def hotels(_: HotelSearch) -> TravelReport:
            return TravelReport(provider="kiwi", status="no_results")

        turn = TravelService(flights=flights, hotels=hotels).new_turn(asyncio.get_running_loop().time() + 30, today=DAY)
        with capture_logs() as logs:
            results = await asyncio.gather(turn.search_flights(ROUTE), turn.search_hotels(STAY))
        assert [result.status for result in results] == ["unavailable", "invalid_response"]
        assert "private travel information" not in str(logs)

    asyncio.run(check())


def test_rendered_artifact_and_citation_sources_have_one_shared_size_boundary() -> None:
    """Large provider links cannot make the visible artifact exceed its byte budget."""
    offers = tuple(
        TravelOffer(title=f"Trip {i}", url=f"https://www.kiwi.com/search/{i}?" + "a" * 7900) for i in range(5)
    )
    original = TravelReport(provider="kiwi", status="found", offers=offers, checked_at=datetime.now(UTC))
    record = TravelCallRecord(5, original.bounded())
    content = record.report.model_dump_json()
    assert len(content.encode()) <= 24000
    assert record.report.status == "partial"
    assert len(record.sources) == len(record.report.offers) < len(offers)
    assert all(url in content for url in record.sources)


def test_a_search_without_a_currency_takes_the_visitor_s() -> None:
    """An en-GB visitor's search in pounds when the model leaves currency out; a currency the model names stays."""

    async def check() -> None:
        asked: list[str] = []

        async def flights(query: FlightSearch) -> TravelReport:
            asked.append(query.currency)
            return _flight_result()

        turn = TravelService(flights=flights).new_turn(
            asyncio.get_running_loop().time() + 30, today=DAY, currency="GBP"
        )
        await turn.search_flights(
            FlightSearch.model_validate({"origin": "LHR", "destination": "LAS", "departure_date": DAY})
        )
        await turn.search_flights(
            FlightSearch.model_validate(
                {"origin": "LGW", "destination": "LAS", "departure_date": DAY, "currency": "USD"}
            )
        )
        assert asked == ["GBP", "USD"]

    asyncio.run(check())
