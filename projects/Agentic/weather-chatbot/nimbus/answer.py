"""
nimbus/answer.py: the answer: the model's words as it writes them, within the answer's caps, with its tokens counted
and every failure turned into one of our errors; and the finished answer's Markdown, made into HTML that can only ever
be text and links.
"""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import cast

from langchain_core.exceptions import (
    ModelAuthenticationError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)
from langchain_core.exceptions import ModelTimeoutError as LangChainModelTimeoutError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langsmith import tracing_context
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

from nimbus.constants import ANSWER_TIMEOUT_SECONDS
from nimbus.errors import AnswerTimeoutError, ConfigError, ModelBusyError, ModelFailedError, NimbusError
from nimbus.model import Tracer

# What a link in an answer carries: it opens in a new tab, so the chat stays, and it tells the other site nothing.
LINK_REL = "nofollow noopener noreferrer"
# How Gemini says a key isn't one: a 400 whose details give this reason (it names no provider's class here).
BAD_KEY_REASON = "API_KEY_INVALID"


@dataclass
class AnswerStats:
    """What the model reported about an answer: its tokens in and out, added up chunk by chunk."""

    tokens_in: int = 0
    tokens_out: int = 0


def is_set_up_wrong(error: BaseException) -> bool:
    """
    Whether a model's error says this deployment is set up wrong: a key refused (401, 403, or Gemini's 400 with
    API_KEY_INVALID), or a model name the provider doesn't know (404).
    """
    if isinstance(error, (ModelAuthenticationError, ModelPermissionDeniedError, ModelNotFoundError)):
        return True
    return isinstance(error, ModelInvalidRequestError) and BAD_KEY_REASON in f"{error} {error.__cause__}"


async def stream_answer(
    model: BaseChatModel,
    messages: Sequence[BaseMessage],
    stats: AnswerStats,
    tracer: Tracer | None,
) -> AsyncGenerator[str]:
    """
    The answer's text, a piece at a time as the model writes it, within 30 s in all; LangSmith traces the run only
    with a tracer, whose client hides its inputs and outputs, in its project. A failure becomes ours: ModelBusyError,
    AnswerTimeoutError, ConfigError or ModelFailedError.
    """
    deadline = asyncio.get_running_loop().time() + ANSWER_TIMEOUT_SECONDS
    client, project = (tracer.client, tracer.project) if tracer is not None else (None, None)
    try:
        with tracing_context(enabled=tracer is not None, client=client, project_name=project):
            # The model's stream is closed however this one ends, so its call to Gemini never outlives the answer. It
            # is an async generator, though LangChain types it as an iterator, which has no aclose().
            stream = cast("AsyncGenerator[AIMessageChunk]", model.astream(messages))
            async with aclosing(stream) as chunks:
                while True:
                    # ① The next chunk, before the deadline: only this wait is timed, never the time the page takes
                    # between two pieces, so a deadline that passes lands here, as ours to name (issue 38).
                    async with asyncio.timeout_at(deadline):
                        chunk = await anext(chunks, None)
                    if chunk is None:
                        return
                    # ② Each chunk's share of the tokens, added up.
                    if chunk.usage_metadata is not None:
                        stats.tokens_in += chunk.usage_metadata["input_tokens"]
                        stats.tokens_out += chunk.usage_metadata["output_tokens"]
                    # ③ The words, as they come.
                    if chunk.text:
                        yield chunk.text
    # ④ A failure, as one of ours; the model's own error is kept as its cause, for the logs' class.
    except NimbusError:
        raise
    except (TimeoutError, LangChainModelTimeoutError) as error:
        raise AnswerTimeoutError from error
    except ModelRateLimitError as error:
        raise ModelBusyError from error
    except Exception as error:
        if is_set_up_wrong(error):
            raise ConfigError from error
        raise ModelFailedError from error


def _link_open(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    """Renders a link's opening tag: in a new tab, telling the other site nothing (LINK_REL)."""
    tokens[idx].attrSet("rel", LINK_REL)
    tokens[idx].attrSet("target", "_blank")
    return renderer.renderToken(tokens, idx, options, env)


def _create_markdown() -> MarkdownIt:
    """CommonMark with raw HTML off and pictures off: an answer can hold text, emphasis, lists, code and links."""
    markdown = MarkdownIt("commonmark", {"html": False}).disable("image")
    markdown.add_render_rule("link_open", _link_open)
    return markdown


ANSWER_MARKDOWN = _create_markdown()


def render_answer(text: str) -> Markup:
    """
    The finished answer's HTML, from the model's Markdown. Safe to put in a template as it is: with raw HTML off, every
    tag in it is markdown-it's own, and markdown-it never makes a link of a javascript: address.
    """
    return Markup(ANSWER_MARKDOWN.render(text))  # noqa: S704
