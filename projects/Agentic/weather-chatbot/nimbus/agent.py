"""
nimbus/agent.py: the agent (step 4): LangChain's prebuilt one, create_agent(), a LangGraph graph of two nodes. "model"
calls the model with the tools; when the model asks for tools, "tools" runs each call on its own, and the model is
called again with the results; when the model answers in words, the run ends. At most 5 calls to the model: a sixth
fails the answer. Step 5 replaces it with a graph of our own, whose last call gets no tools.
"""

from collections.abc import Sequence
from typing import Any, Final

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from nimbus.constants import AGENT_NAME, AGENT_RECURSION_LIMIT, LANE_ID

# Each run's settings: the step limit (the prebuilt agent's own is 9,999), and, for LangSmith, the lane as a tag. The
# run is named after the agent: "nimbus".
AGENT_CONFIG: Final[RunnableConfig] = {
    "recursion_limit": AGENT_RECURSION_LIMIT,
    "tags": [LANE_ID],
    "metadata": {"lane": LANE_ID},
}


def make_agent(model: BaseChatModel, tools: Sequence[BaseTool]) -> CompiledStateGraph[Any, Any, Any, Any]:
    """The prebuilt agent, for one answer: the model and this answer's tools. Building one takes about 1.5 ms."""
    return create_agent(model, list(tools), name=AGENT_NAME)
