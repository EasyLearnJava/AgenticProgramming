"""
nimbus/agent.py: the agent (step 5): a LangGraph graph of our own, two nodes in a loop. "model" calls Gemini with the
tools; when Gemini asks for tools, each call goes to "tools" as a task of its own, and the model is called again with
the results; when Gemini answers in words, the run ends. The fifth call to the model has its tools turned off, so every
answer ends in words, never on a failure; each call's first words must come within 10 s.
"""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from typing import Any, Final, cast

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.utils import message_chunk_to_message
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Send

from nimbus.constants import AGENT_NAME, AGENT_RECURSION_LIMIT, LANE_ID, MAX_MODEL_CALLS, MODEL_FIRST_CHUNK_SECONDS

# Each run's settings: LangGraph's recursion limit, a backstop the graph never reaches, and, for LangSmith, the lane as
# a tag. The run is named after the graph: "nimbus".
AGENT_CONFIG: Final[RunnableConfig] = {
    "recursion_limit": AGENT_RECURSION_LIMIT,
    "tags": [LANE_ID],
    "metadata": {"lane": LANE_ID},
}


class AgentState(MessagesState, total=False):
    """The run's state: the conversation so far, and how many times the model has been called."""

    model_calls: int


async def _first_words_in_time(
    model: Runnable[LanguageModelInput, BaseMessage], messages: Sequence[BaseMessage]
) -> BaseMessage:
    """
    One call's whole message, streamed: its first chunk within 10 s, or the answer ends as too slow; then the rest,
    within the answer's own deadline. LangGraph passes each chunk on to the page as it comes.
    """
    stream = cast("AsyncGenerator[AIMessageChunk]", model.astream(messages))
    async with aclosing(stream) as chunks:
        async with asyncio.timeout(MODEL_FIRST_CHUNK_SECONDS):
            message = await anext(chunks, None)
        if message is None:
            return AIMessage(content="")
        async for chunk in chunks:
            message += chunk
    return message_chunk_to_message(message)


def make_agent(model: BaseChatModel, tools: Sequence[BaseTool]) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Our graph, for one answer: the model, and this answer's tools, which hold its HTTP client."""

    async def call_model(state: AgentState) -> dict[str, Any]:
        """① One call to the model: with the tools, or, the fifth time, with calling them turned off."""
        calls = state.get("model_calls", 0) + 1
        bound = model.bind_tools(tools, tool_choice="none" if calls >= MAX_MODEL_CALLS else "auto")
        return {"messages": [await _first_words_in_time(bound, state["messages"])], "model_calls": calls}

    def route(state: AgentState) -> list[Send] | str:
        """② After a call: each tool call the model asked for to "tools", as a task of its own; words end the run."""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return [Send("tools", [call]) for call in last.tool_calls]
        return END

    # ③ The graph: the model first; then tools and the model in turn, until the model answers in words.
    graph = StateGraph(AgentState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(list(tools)))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route, ["tools", END])
    graph.add_edge("tools", "model")
    return graph.compile(name=AGENT_NAME)
