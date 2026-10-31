"""
nimbus/lanes.py: the lanes, the ways the agent reaches its four tools: REST or MCP, without auth or with it. REST · no
auth (step 4) calls Open-Meteo from the chat's own function; MCP · no auth (step 9) calls our own MCP server, on this
same deployment, which calls Open-Meteo. The two with auth open in step 10; until then the page shows them, closed.
"""

from dataclasses import dataclass
from typing import Final, Literal

# The lanes a question can take: the form's value, checked (chat.py).
OpenLaneId = Literal["rest-no-auth", "mcp-no-auth"]


@dataclass(frozen=True)
class Lane:
    """A lane: its id, for the form and the logs; its label, its door, whether it has auth, and the step it opens in."""

    id: str
    label: str
    door: Literal["REST", "MCP"]
    auth: bool
    step: int
    is_open: bool


REST_NO_AUTH: Final = Lane("rest-no-auth", "REST · no auth", "REST", auth=False, step=4, is_open=True)
MCP_NO_AUTH: Final = Lane("mcp-no-auth", "MCP · no auth", "MCP", auth=False, step=9, is_open=True)
REST_WITH_AUTH: Final = Lane("rest-with-auth", "REST · with auth", "REST", auth=True, step=10, is_open=False)
MCP_WITH_AUTH: Final = Lane("mcp-with-auth", "MCP · with auth", "MCP", auth=True, step=10, is_open=False)
# The picker's order, a row for each door: REST without auth and with it, then MCP's two.
LANES: Final = (REST_NO_AUTH, REST_WITH_AUTH, MCP_NO_AUTH, MCP_WITH_AUTH)


def get_lane(lane_id: str) -> Lane:
    """The lane with the id."""
    return next(lane for lane in LANES if lane.id == lane_id)
