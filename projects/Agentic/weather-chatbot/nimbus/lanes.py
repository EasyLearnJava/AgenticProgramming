"""
nimbus/lanes.py: the lanes, the ways the agent reaches its four tools: REST or MCP, without auth or with it. REST · no
auth (step 4) calls Open-Meteo from the chat's own function; MCP · no auth (step 9) calls our own MCP server, on this
same deployment, which calls Open-Meteo. The two with auth (step 10) run the forecast through Apify's Actor, behind
Apify's token, each falling back to its twin with no auth: without a token, they're closed.
"""

from dataclasses import dataclass
from typing import Final, Literal

from nimbus.config import Settings

# The lanes a form may name; one with auth is open only with Apify's token (chat.py).
LaneId = Literal["rest-no-auth", "mcp-no-auth", "rest-with-auth", "mcp-with-auth"]


@dataclass(frozen=True)
class Lane:
    """A lane: its id, for the form and the logs; its label, its door, whether it has auth, and the step it opens in."""

    id: str
    label: str
    door: Literal["REST", "MCP"]
    auth: bool
    step: int


REST_NO_AUTH: Final = Lane("rest-no-auth", "REST · no auth", "REST", auth=False, step=4)
MCP_NO_AUTH: Final = Lane("mcp-no-auth", "MCP · no auth", "MCP", auth=False, step=9)
REST_WITH_AUTH: Final = Lane("rest-with-auth", "REST · with auth", "REST", auth=True, step=10)
MCP_WITH_AUTH: Final = Lane("mcp-with-auth", "MCP · with auth", "MCP", auth=True, step=10)
# The picker's order, a row for each door: REST without auth and with it, then MCP's two.
LANES: Final = (REST_NO_AUTH, REST_WITH_AUTH, MCP_NO_AUTH, MCP_WITH_AUTH)


def get_lane(lane_id: str) -> Lane:
    """The lane with the id."""
    return next(lane for lane in LANES if lane.id == lane_id)


def is_open(lane: Lane, settings: Settings) -> bool:
    """Whether a question can take the lane on this deployment: one with auth needs Apify's token."""
    return not lane.auth or settings.apify_token is not None
