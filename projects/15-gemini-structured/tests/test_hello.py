"""Tests for project 15. The plain tests make no model call: the two schemas (what Gemini is told, and what Pydantic
accepts), the model's settings, how the chains are built, turning JSON into objects, the endpoints with a stand-in,
and the page. The live tests ask Gemini for one greeting and one ticket and check they're real, typed objects."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

import main
from hello import (LANGUAGES, MAX_OUTPUT_TOKENS, MODEL, SAMPLE_MESSAGE, Greeting, Ticket, api_key, greet_chain,
                   greet_prompt, model, triage_chain, triage_prompt)

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent

A_GREETING = {"message": "Welcome, Asha!", "language": "English", "emoji": "👋", "tone": "warm"}
A_TICKET = {"intent": "Refund a double charge", "category": "billing", "urgency": "high",
            "route_to_team": "billing_team"}


# ---- the schemas, no call ----

def test_the_greeting_schema_lists_every_field_as_required_with_its_choices():
    schema = Greeting.model_json_schema()
    assert schema["required"] == ["message", "language", "emoji", "tone"]
    assert schema["properties"]["tone"]["enum"] == ["warm", "playful", "formal"]
    assert schema["properties"]["language"]["enum"] == LANGUAGES
    assert "requested language" in schema["properties"]["message"]["description"]   # Gemini reads this


def test_the_ticket_schema_lists_the_choices_for_category_urgency_and_team():
    properties = Ticket.model_json_schema()["properties"]
    assert properties["category"]["enum"] == ["billing", "technical", "account", "shipping", "other"]
    assert properties["urgency"]["enum"] == ["low", "medium", "high"]
    assert "billing_team" in properties["route_to_team"]["enum"]
    assert "money lost" in properties["urgency"]["description"]      # the rule for "high", which Gemini reads


def test_pydantic_accepts_data_that_fits():
    assert Greeting(**A_GREETING).tone == "warm"
    assert Ticket(**A_TICKET).urgency == "high"


@pytest.mark.parametrize("change", [
    {"tone": "angry"},                 # not one of the three tones
    {"language": "Klingon"},           # not one of the languages
    {"emoji": None},                   # not a string
])
def test_pydantic_rejects_a_greeting_that_does_not_fit(change):
    with pytest.raises(ValidationError):
        Greeting(**{**A_GREETING, **change})


def test_pydantic_rejects_a_ticket_with_a_missing_field():
    with pytest.raises(ValidationError):
        Ticket(**{k: v for k, v in A_TICKET.items() if k != "urgency"})


# ---- the model and the chains, no call ----

def test_model_settings():
    assert model.model == MODEL == "gemini-3.5-flash-lite"
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS == 300


def test_each_chain_is_prompt_then_model_then_a_pydantic_parser():
    for chain, prompt, schema in [(greet_chain, greet_prompt, Greeting), (triage_chain, triage_prompt, Ticket)]:
        assert chain.first is prompt
        parser = chain.last
        assert isinstance(parser, PydanticOutputParser)
        assert parser.pydantic_object is schema


def test_the_model_is_asked_for_json_in_the_schemas_shape():
    bound_model = greet_chain.middle[0]          # the step between the prompt and the parser
    assert bound_model.bound is model            # our model, with two settings bound to it for this chain
    assert bound_model.kwargs["response_mime_type"] == "application/json"
    assert bound_model.kwargs["response_json_schema"] == Greeting.model_json_schema()


def test_the_parser_turns_geminis_json_into_an_object():
    reply = AIMessage(content='{"message": "Welcome, Asha!", "language": "English", "emoji": "👋", "tone": "warm"}')
    greeting = greet_chain.last.invoke(reply)
    assert isinstance(greeting, Greeting)
    assert greeting.message == "Welcome, Asha!"


def test_the_parser_refuses_json_that_does_not_fit():
    reply = AIMessage(content='{"message": "Welcome!", "language": "English", "emoji": "👋", "tone": "angry"}')
    with pytest.raises(OutputParserException, match="tone"):
        greet_chain.last.invoke(reply)


def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    # A copy of the environment with the key set to "". load_dotenv() doesn't replace a variable that is already set,
    # so hello.py finds no key even when there is a .env file.
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoints, with the chains swapped out so no call is made ----

def test_api_setup_gives_the_languages_and_the_sample_message():
    assert client.get("/api/setup").json() == {"languages": LANGUAGES, "sample_message": SAMPLE_MESSAGE}


def test_api_greet_returns_every_field(monkeypatch):
    seen = {}

    def fake_greet_chain(inputs):
        seen.update(inputs)                  # remember what the endpoint passed to the chain
        return Greeting(**A_GREETING)

    monkeypatch.setattr(main, "greet_chain", RunnableLambda(fake_greet_chain))
    response = client.post("/api/greet", json={"name": " Asha ", "language": "English"})
    assert response.status_code == 200
    assert response.json() == A_GREETING
    assert seen == {"name": "Asha", "language": "English"}      # the spaces around the name were trimmed


def test_api_triage_returns_every_field(monkeypatch):
    monkeypatch.setattr(main, "triage_chain", RunnableLambda(lambda inputs: Ticket(**A_TICKET)))
    response = client.post("/api/triage", json={"message": SAMPLE_MESSAGE})
    assert response.status_code == 200
    assert response.json() == A_TICKET


@pytest.mark.parametrize("url, body, field", [
    ("/api/greet", {"name": "", "language": "English"}, "name"),
    ("/api/greet", {"name": "Asha", "language": "Klingon"}, "language"),
    ("/api/triage", {"message": "x" * 1001}, "message"),
])
def test_bad_input_gets_a_422_and_no_model_call(monkeypatch, url, body, field):
    def must_not_run(inputs):
        raise AssertionError("the model was called for a bad request")
    monkeypatch.setattr(main, "greet_chain", RunnableLambda(must_not_run))
    monkeypatch.setattr(main, "triage_chain", RunnableLambda(must_not_run))
    response = client.post(url, json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


def test_an_answer_that_does_not_fit_the_schema_is_a_502(monkeypatch):
    def gemini_answers_with_a_wrong_tone(prompt_value):
        # A stand-in for the model: real JSON, but "angry" isn't one of the three tones.
        return AIMessage(content='{"message": "Welcome!", "language": "English", "emoji": "👋", "tone": "angry"}')

    # The real prompt and the real parser, with only the Gemini call replaced.
    chain = greet_prompt | RunnableLambda(gemini_answers_with_a_wrong_tone) | greet_chain.last
    monkeypatch.setattr(main, "greet_chain", chain)
    response = client.post("/api/greet", json={"name": "Asha", "language": "English"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (OutputParserException)."}


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="greet-fields"' in response.text
    assert 'id="triage-fields"' in response.text
    assert api_key not in response.text


def test_page_checks_res_ok_on_load_and_on_submit():
    # fetch() doesn't fail on an error answer such as a 500 (the server did answer), so the page checks res.ok itself:
    # once for GET /api/setup when it opens, and once in the submit handler that both forms share.
    page = (FOLDER / "index.html").read_text(encoding="utf-8")
    assert page.count("throw new Error(`the server answered HTTP ${res.status}`);") == 2
    assert "`Something went wrong: ${err.message}`" in page


# ---- live: one greeting and one ticket ----

@pytest.mark.live
def test_live_gemini_returns_a_typed_greeting():
    greeting = greet_chain.invoke({"name": "Asha", "language": "Spanish"})
    assert isinstance(greeting, Greeting)                # already checked by Pydantic: every field, every choice
    assert greeting.language == "Spanish"
    assert greeting.message.strip() and greeting.emoji.strip()


@pytest.mark.live
def test_live_a_double_charge_is_sorted_as_billing():
    ticket = triage_chain.invoke({"message": SAMPLE_MESSAGE})
    assert isinstance(ticket, Ticket)
    assert ticket.category == "billing"
    assert ticket.intent.strip()
