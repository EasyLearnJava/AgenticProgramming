"""
Tests for src/llm/llm_client.py: one call, sync or async, giving the answer with its token counts and why it stopped,
all on the span's line; an empty answer refused, one cut off at the cap logged; Gemini's model built with its
settings; and a provider's failures each turned into the right UpstreamError, with the real LangChain Gemini class
running against Google's client faked, so nothing leaves the machine.
"""
import asyncio

import httpx
import pytest
from fakes import FakeGenaiClient, gemini_answer, reply
from google.genai import errors
from langchain_core.language_models.fake_chat_models import FakeListChatModel, FakeMessagesListChatModel
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from src.config.settings import load_settings
from src.exceptions import UpstreamDailyQuotaError, UpstreamError, UpstreamRateLimitError, UpstreamTimeoutError
from src.llm.llm_client import LLMClient, LLMResponse, create_chat_model

MESSAGES = [HumanMessage("My VPN won't connect")]


def gemini_client(client: FakeGenaiClient) -> LLMClient:
    """The real Gemini chat model, as config.yaml makes it, with Google's client faked."""
    model = create_chat_model(load_settings().llm, SecretStr("fake-key"))
    model.client = client
    return LLMClient(model)


def test_the_answer_comes_with_its_tokens_and_why_it_stopped(logs):
    llm = LLMClient(FakeMessagesListChatModel(responses=[reply("  Open the ports.  ")]))
    assert llm.generate(MESSAGES) == LLMResponse(text="Open the ports.", finish_reason="STOP", input_tokens=950,
                                                 output_tokens=12)
    record = logs.find("llm.generate ok")
    assert (record.model, record.input_tokens, record.output_tokens, record.finish_reason) == (
        "FakeMessagesListChatModel", 950, 12, "STOP")


def test_agenerate_gives_the_same():
    replies = [reply("Open the ports.")] * 2
    llm = LLMClient(FakeMessagesListChatModel(responses=replies))
    assert asyncio.run(llm.agenerate(MESSAGES)) == llm.generate(MESSAGES)


def test_a_model_that_reports_nothing_still_answers():
    response = LLMClient(FakeListChatModel(responses=["An answer."])).generate(MESSAGES)
    assert (response.text, response.finish_reason, response.input_tokens) == ("An answer.", None, None)


def test_an_empty_answer_is_an_error():
    llm = LLMClient(FakeMessagesListChatModel(responses=[reply("", finish_reason="SAFETY")]))
    with pytest.raises(UpstreamError, match="the model returned no text \\(finish_reason SAFETY\\)"):
        llm.generate(MESSAGES)


def test_an_answer_cut_off_at_the_cap_is_logged(logs):
    LLMClient(FakeMessagesListChatModel(responses=[reply("Step 1: open the", finish_reason="MAX_TOKENS")])).generate(
        MESSAGES)
    assert logs.find("The answer was cut off at llm.max_output_tokens").levelname == "WARNING"


# --- Gemini's model ---

def test_gemini_is_built_with_the_settings():
    model = create_chat_model(load_settings().llm, SecretStr("fake-key"))
    assert (model.model, model.max_output_tokens, model.timeout, model.max_retries) == (
        "gemini-3.5-flash-lite", 500, 30, 3)
    assert model.temperature is None           # this model has fixed sampling: see the comment in llm_client.py


def test_the_real_gemini_class_runs_end_to_end_with_googles_client_faked():
    llm = gemini_client(FakeGenaiClient(generate=gemini_answer("Open UDP ports 500 and 4500.")))
    expected = LLMResponse(text="Open UDP ports 500 and 4500.", finish_reason="STOP", input_tokens=950,
                           output_tokens=12)
    assert llm.generate(MESSAGES) == expected
    assert asyncio.run(llm.agenerate(MESSAGES)) == expected
    assert llm.model_name == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("error, expected, retryable", [
    (errors.ClientError(429, {"error": {"code": 429, "message": "Quota.", "status": "RESOURCE_EXHAUSTED"}}),
     UpstreamRateLimitError, True),
    (errors.ClientError(429, {"error": {"code": 429, "message": "Quota.", "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}),
     UpstreamDailyQuotaError, True),
    (httpx.ReadTimeout("The read operation timed out"), UpstreamTimeoutError, True),
    (errors.ServerError(503, {"error": {"code": 503, "message": "Overloaded.", "status": "UNAVAILABLE"}}),
     UpstreamError, True),
    (errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}}),
     UpstreamError, False),
], ids=["rate limit", "the day's quota", "timeout", "server error", "bad key"])
def test_each_provider_failure_becomes_the_right_upstream_error(error, expected, retryable, logs):
    llm = gemini_client(FakeGenaiClient(generate=error))
    for call in (lambda: llm.generate(MESSAGES), lambda: asyncio.run(llm.agenerate(MESSAGES))):
        with pytest.raises(UpstreamError) as caught:
            call()
        assert type(caught.value) is expected
        assert (caught.value.service, caught.value.retryable) == ("llm", retryable)
    assert logs.find("llm.generate failed").error_type == expected.__name__
