"""Synthetic quotes for the HTTP and browser acceptance tests."""

from decimal import Decimal

from nimbus.travel.models import FlightSearch, HotelSearch, TravelOffer, TravelReport
from nimbus.travel.service import TravelService

FLIGHT_LINK = "https://www.kiwi.com/en/booking/synthetic"


def travel_service() -> TravelService:
    """Produce two different provider outcomes without credentials or external calls."""

    async def flights(_query: FlightSearch) -> TravelReport:
        """A verified party fare and its specific booking link."""
        return TravelReport(
            provider="kiwi",
            status="found",
            offers=(
                TravelOffer(
                    title="Synthetic round trip",
                    price=Decimal("395.00"),
                    currency="USD",
                    price_basis="party_total",
                    url=FLIGHT_LINK,
                ),
            ),
        )

    async def hotels(_query: HotelSearch) -> TravelReport:
        """A temporary refusal with no offers."""
        return TravelReport(provider="trivago", status="rate_limited")

    return TravelService(flights=flights, hotels=hotels)
