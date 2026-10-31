"""
tests/fakes.py: a stand-in for Gemini, for the unit and browser tests: a LangChain chat model that streams a known
answer a word at a time, after a pause each, reports each chunk's share of the tokens as Gemini does (a delta, not a
running total), says whether its stream was closed, and can fail on cue. The tests never call the real model: it needs
a key, and it costs quota.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

ANSWER = (
    "Hi, I'm Nimbus. I can't check the **weather** yet: live forecasts come in a later step. Ask me how weather "
    "works, or what a forecast term means, and I'll explain it in plain words."
)
# A word, with the space before it.
PIECE = re.compile(r"\s*\S+")
# The tokens in: the prompt, all in the first chunk. The tokens out: one a word, a chunk at a time.
TOKENS_IN = 412
TOKENS_OUT = len(PIECE.findall(ANSWER))


class FakeModel(BaseChatModel):
    """A chat model that streams its answer a word at a time; it keeps every list of messages it was given."""

    answer: str = ANSWER
    delay: float = 0.0
    fail_after_first_word: BaseException | None = None
    seen: list[list[BaseMessage]] = Field(default_factory=list)
    closed: bool = False

    @property
    def _llm_type(self) -> str:
        """The model's kind, for LangChain."""
        return "nimbus-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """The whole answer at once (the app only streams)."""
        self.seen.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.answer))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Not used: the app streams with astream()."""
        raise NotImplementedError

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """The answer, a word at a time, each after the pause, with its share of the tokens; marks itself closed."""
        self.seen.append(messages)
        try:
            for index, piece in enumerate(PIECE.findall(self.answer)):
                await asyncio.sleep(self.delay)
                tokens_in = TOKENS_IN if index == 0 else 0
                usage = UsageMetadata(input_tokens=tokens_in, output_tokens=1, total_tokens=tokens_in + 1)
                yield ChatGenerationChunk(message=AIMessageChunk(content=piece, usage_metadata=usage))
                if index == 0 and self.fail_after_first_word is not None:
                    raise self.fail_after_first_word
        finally:
            self.closed = True
