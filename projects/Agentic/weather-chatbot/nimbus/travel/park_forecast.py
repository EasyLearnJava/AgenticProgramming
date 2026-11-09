"""Fetch a park forecast through the same weather lane for chat briefings and confirmed plans."""

from contextlib import AbstractAsyncContextManager
from typing import Literal

from langchain_core.tools import StructuredTool

from nimbus.parks import Destination
from nimbus.tools import GET_FORECAST, ForecastInput, ForecastOutput
from nimbus.utils import to_unit_system


async def park_forecast(
    destination: Destination,
    days: int,
    locale: str,
    lane_tools: AbstractAsyncContextManager[list[StructuredTool]],
    *,
    unit_system: Literal["", "metric", "imperial"] = "",
) -> ForecastOutput:
    """Use the registry coordinates and visitor's preferred units."""
    params = ForecastInput(
        latitude=destination.latitude,
        longitude=destination.longitude,
        days=days,
        include_hourly=False,
        units=unit_system or to_unit_system(locale),
    )
    async with lane_tools as tools:
        forecast = next(tool for tool in tools if tool.name == GET_FORECAST.name)
        return ForecastOutput.model_validate_json(await forecast.ainvoke(params.model_dump()))
