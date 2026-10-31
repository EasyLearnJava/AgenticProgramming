"""
nimbus/model.py: the model that answers: Gemini, through LangChain's ChatGoogleGenerativeAI, made once when the app
starts, with the caps on each answer; and LangSmith's client, which may trace its runs, hiding their inputs and outputs.
"""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import Client

from nimbus.config import Settings
from nimbus.constants import MAX_OUTPUT_TOKENS, MODEL_MAX_ATTEMPTS, MODEL_REQUEST_TIMEOUT_SECONDS, MODEL_THINKING


def make_chat_model(settings: Settings) -> BaseChatModel | None:
    """Gemini, ready to stream, with the caps on each answer; None on a deployment that has no key for it."""
    if settings.google_api_key is None:
        return None
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=settings.google_api_key,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
        max_retries=MODEL_MAX_ATTEMPTS,
        thinking_level=MODEL_THINKING,
    )


def is_tracing_allowed(settings: Settings) -> bool:
    """
    Whether LangSmith may trace the model's runs: only when tracing is on, with a key, and LangSmith's variables say to
    hide both each run's inputs and its outputs.
    """
    return (
        settings.langsmith_tracing
        and settings.langsmith_api_key is not None
        and settings.langsmith_hide_inputs
        and settings.langsmith_hide_outputs
    )


@dataclass(frozen=True)
class Tracer:
    """Where the model's runs are traced: LangSmith's client, and the project, or LangSmith's default when None."""

    client: Client
    project: str | None


def make_tracer(settings: Settings) -> Tracer | None:
    """
    LangSmith's client and project for the model's runs, when tracing is allowed; else None. The client hides every
    run's inputs and outputs itself, whatever LangSmith's own variables say: its default client hides only for the
    exact string "true", while the app's settings take any true value (issue 34).
    """
    if not is_tracing_allowed(settings) or settings.langsmith_api_key is None:
        return None
    client = Client(api_key=settings.langsmith_api_key.get_secret_value(), hide_inputs=True, hide_outputs=True)
    return Tracer(client=client, project=settings.langsmith_project)
