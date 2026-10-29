"""
IT Knowledge Base: The LLM Client
=================================

Asks the chat model config.yaml names for an answer, and records what the call cost. It handles:
  1. Building the provider's model from its settings: an answer-length cap, a timeout on each call, and a limited
     number of attempts
  2. One call, sync or async, timed in a span with the model, its tokens in and out, and why it stopped
  3. An empty answer, or one cut off at the length cap, logged; any provider failure turned into an UpstreamError

To add a provider: write a builder like _google() and add it to BUILDERS; the rest of the app only sees LangChain's
BaseChatModel interface.

Usage:
    llm = LLMClient(create_chat_model(settings.llm, api_key))
    response = llm.generate(messages)            ->  LLMResponse: text, finish_reason, input_tokens, output_tokens
    response = await llm.agenerate(messages)     ->  the same, for async code
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from src.config.settings import LLMSettings
from src.exceptions import UpstreamError, upstream_error
from src.observability.tracing import span

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Providers
# -------------------------------------------------

def _google(settings: LLMSettings, api_key: SecretStr) -> BaseChatModel:
    """Gemini's chat model. No temperature: gemini-3.5-flash-lite has fixed sampling, and LangChain drops one given
    to it, with a warning."""
    # max_retries is the number of attempts, the first one included (LangChain hands it to Google's client as that)
    return ChatGoogleGenerativeAI(model=settings.model, api_key=api_key, max_output_tokens=settings.max_output_tokens,
                                  timeout=settings.timeout_seconds, max_retries=settings.max_attempts)


BUILDERS: dict[str, Callable[[LLMSettings, SecretStr], BaseChatModel]] = {"google": _google}


def create_chat_model(settings: LLMSettings, api_key: SecretStr) -> BaseChatModel:
    """The chat model config.yaml names. Building it makes no call to the provider."""
    return BUILDERS[settings.provider](settings, api_key)


# -------------------------------------------------
# LLMClient Class - One Call to the Model
# -------------------------------------------------

@dataclass(frozen=True)
class LLMResponse:
    """The model's answer, and what the call reported: None where the model doesn't say."""
    text: str
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None


class LLMClient:
    """
    Calls any LangChain chat model: timed, with its token counts logged, and its failures turned into UpstreamError.

    Step 1: Configure: the constructor stores the model; no call is made
    Step 2: Call: generate() or agenerate() with the prompt's messages
    """

    def __init__(self, model: BaseChatModel):
        self.model = model
        # Gemini's models know their name (.model); a stand-in goes by its class name
        self.model_name: str = getattr(model, "model", type(model).__name__)

    def generate(self, messages: list[BaseMessage]) -> LLMResponse:
        """The model's answer to the messages. Raises UpstreamError."""
        with span("llm.generate", model=self.model_name) as fields:
            try:
                message = self.model.invoke(messages)
            except Exception as err:
                raise upstream_error("llm", err) from err
            return self._response(message, fields)

    async def agenerate(self, messages: list[BaseMessage]) -> LLMResponse:
        """The same, for async code: the server can do other work while the model answers."""
        with span("llm.generate", model=self.model_name) as fields:
            try:
                message = await self.model.ainvoke(messages)
            except Exception as err:
                raise upstream_error("llm", err) from err
            return self._response(message, fields)

    @staticmethod
    def _response(message: BaseMessage, fields: dict[str, Any]) -> LLMResponse:
        """The reply's text and what the provider reported about it; an empty reply is an error."""
        usage = getattr(message, "usage_metadata", None) or {}
        response = LLMResponse(text=message.text.strip(), finish_reason=message.response_metadata.get("finish_reason"),
                               input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"))
        fields.update(finish_reason=response.finish_reason, input_tokens=response.input_tokens,
                      output_tokens=response.output_tokens)
        if not response.text:
            # Often a reply blocked for safety, or all of max_output_tokens spent before any text
            raise UpstreamError("llm", f"the model returned no text (finish_reason {response.finish_reason})")
        if response.finish_reason == "MAX_TOKENS":
            logger.warning("The answer was cut off at llm.max_output_tokens", extra={"output_tokens":
                                                                                         response.output_tokens})
        return response
