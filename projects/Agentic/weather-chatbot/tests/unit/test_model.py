"""
tests/unit/test_model.py: the model: none without a key; Gemini with the answer's caps when there is one, its key never
shown; and LangSmith may trace only when it hides both a run's inputs and its outputs, into the project we name.
"""

import json

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from nimbus import model as model_module
from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.model import is_tracing_allowed, make_chat_model, make_tracer

KEY = "test-key-not-a-real-one"
PROJECT = "nimbus-tests"


def test_no_key_no_model() -> None:
    assert make_chat_model(Settings(_env_file=None)) is None


def test_the_app_says_how_it_starts_and_never_its_key(capsys: pytest.CaptureFixture[str]) -> None:
    # Read from stdout: building the app sets logging up afresh, which would undo capture_logs() (issue 23).
    create_app(Settings(_env_file=None, google_api_key=SecretStr(KEY)))
    out = capsys.readouterr().out
    [started] = [json.loads(line) for line in out.splitlines() if '"app.started"' in line]
    assert started["modelSetUp"] is True
    assert started["tracing"] is False
    assert started["model"] == "gemini-3.5-flash-lite"
    assert KEY not in out


def test_with_a_key_gemini_with_the_answer_s_caps() -> None:
    model = make_chat_model(Settings(_env_file=None, google_api_key=SecretStr(KEY)))
    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model.endswith("gemini-3.5-flash-lite")
    # The caps, in numbers: 1,024 tokens out, 20 s a call, two attempts (LangChain counts the first; issue 36), and
    # the least thinking, whose tokens count against the 1,024.
    assert (model.max_output_tokens, model.timeout, model.max_retries) == (1024, 20, 2)
    assert model.reasoning_effort == "minimal"
    assert KEY not in repr(model)


def test_another_model_can_be_named() -> None:
    model = make_chat_model(Settings(_env_file=None, google_api_key=SecretStr(KEY), gemini_model="gemini-3.5-flash"))
    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model.endswith("gemini-3.5-flash")


def test_a_model_name_must_look_like_one() -> None:
    with pytest.raises(ValueError, match="gemini_model"):
        Settings(_env_file=None, gemini_model="../evil")


def langsmith(*, tracing: bool = True, key: bool = True, inputs: bool = True, outputs: bool = True) -> Settings:
    """LangSmith's variables: by default tracing on, a key, a project, and both inputs and outputs hidden."""
    return Settings(
        _env_file=None,
        langsmith_tracing=tracing,
        langsmith_api_key=SecretStr(KEY) if key else None,
        langsmith_project=PROJECT,
        langsmith_hide_inputs=inputs,
        langsmith_hide_outputs=outputs,
    )


def test_traces_only_with_tracing_on_a_key_and_both_hidden() -> None:
    assert is_tracing_allowed(langsmith())
    assert not is_tracing_allowed(langsmith(tracing=False))
    assert not is_tracing_allowed(langsmith(key=False))
    assert not is_tracing_allowed(langsmith(inputs=False))
    assert not is_tracing_allowed(langsmith(outputs=False))


class RecordingClient:
    """Stands in for LangSmith's client, which would start a thread that calls LangSmith: it keeps how it was made."""

    def __init__(self, **kwargs: object) -> None:
        """Keeps the arguments."""
        self.kwargs = kwargs


def test_the_tracer_hides_every_run_s_inputs_and_outputs_whatever_its_variables_say(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # LangSmith's own client hides only for the exact string "true"; the app's tracer hides always (issue 34). Its
    # project is the one the app's settings name, from .env.local too (issue 42).
    monkeypatch.setattr(model_module, "Client", RecordingClient)
    tracer = make_tracer(langsmith())
    assert tracer is not None
    assert isinstance(tracer.client, RecordingClient)
    assert tracer.client.kwargs == {"api_key": KEY, "hide_inputs": True, "hide_outputs": True}
    assert tracer.project == PROJECT


def test_no_tracer_when_tracing_isn_t_allowed() -> None:
    assert make_tracer(langsmith(inputs=False)) is None
    assert make_tracer(Settings(_env_file=None)) is None
