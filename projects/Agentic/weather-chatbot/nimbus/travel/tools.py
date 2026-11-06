"""The two small Nimbus search tools. Only reviewed operations and bounded result fields are exposed to Gemini."""

import time
from typing import Any

from langchain_core.tools import StructuredTool

from nimbus.travel.models import FlightSearch, HotelSearch, TravelCallRecord
from nimbus.travel.service import TravelTurn
from nimbus.utils import to_ms

FLIGHT_INPUT_ERROR = "Flight details are invalid. Ask for the route, travel dates and party size."
HOTEL_INPUT_ERROR = "Hotel details are invalid. Ask for the location, dates, rooms and guests."


def make_travel_tools(turn: TravelTurn) -> list[StructuredTool]:
    """Expose the enabled providers with stable, locally owned Gemini-compatible schemas."""

    async def flights(**fields: Any) -> tuple[str, TravelCallRecord]:
        """Look up a flight using the same budget as the trip planner."""
        started = time.perf_counter()
        report = await turn.search_flights(FlightSearch.model_validate(fields))
        return report.model_context(), TravelCallRecord(to_ms(time.perf_counter() - started), report)

    async def hotels(**fields: Any) -> tuple[str, TravelCallRecord]:
        """Look up accommodation using the same budget as the trip planner."""
        started = time.perf_counter()
        report = await turn.search_hotels(HotelSearch.model_validate(fields))
        return report.model_context(), TravelCallRecord(to_ms(time.perf_counter() - started), report)

    tools: list[StructuredTool] = []
    if turn.flights_enabled:
        tools.append(
            StructuredTool.from_function(
                coroutine=flights,
                name="search_flights",
                args_schema=FlightSearch,
                response_format="content_and_artifact",
                description=(
                    "Search Kiwi flights only when travel options are requested. Ask for missing origin, destination, "
                    "departure date, return date for round trips, and party size. Use ISO dates. State the price basis "
                    "and currency from the returned offer. Refer the visitor to the verified offer cards."
                ),
                handle_validation_error=FLIGHT_INPUT_ERROR,
            )
        )
    if turn.hotels_enabled:
        tools.append(
            StructuredTool.from_function(
                coroutine=hotels,
                name="search_hotels",
                args_schema=HotelSearch,
                response_format="content_and_artifact",
                description=(
                    "Search live Trivago hotels for a destination name OR known coordinates. Ask for missing check-in, "
                    "check-out, guests, rooms and child ages. Use ISO dates in check_in and check_out. "
                    "Distinguish nightly rates from stay "
                    "totals. A failed search says nothing about actual availability."
                ),
                handle_validation_error=HOTEL_INPUT_ERROR,
            )
        )
    return tools
