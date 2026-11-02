"""
tests/unit/test_axiom_query.py: the Observability pages' questions to Axiom (step 14), with Axiom played back: a query
POSTed to the edge's query door with its token and its time range; the first table's rows, field by field; no table,
no rows; a table we can't read; each status Axiom may answer with, an Axiom out of reach or past its 5 s, and an
answer that isn't JSON, each by its code, never with the token or Axiom's words.
"""

import asyncio
import json
from datetime import UTC, datetime

import httpx2
import pytest
from pydantic import SecretStr

from nimbus import axiom_query
from nimbus.axiom_query import AxiomQuery, Row, to_rows
from nimbus.constants import AXIOM_QUERY_URL
from nimbus.errors import ObservabilityError
from tests.fakes import AXIOM_WORDS, AxiomRecordings, to_tabular

TOKEN = SecretStr("xaat-query-test")
START = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
END = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def ask(axiom: AxiomRecordings | httpx2.MockTransport, apl: str = "['weather-chatbot'] | take 50") -> list[Row]:
    """The rows Axiom, played back, gives the query."""
    transport = axiom if isinstance(axiom, httpx2.MockTransport) else httpx2.MockTransport(axiom)
    query = AxiomQuery(TOKEN, lambda: httpx2.AsyncClient(transport=transport))
    return asyncio.run(query.run(apl, START, END))


def test_a_query_is_posted_to_the_edge_with_its_token_and_its_time_range() -> None:
    axiom = AxiomRecordings()
    ask(axiom)
    [request] = axiom.requests
    assert (request.method, str(request.url)) == ("POST", AXIOM_QUERY_URL)
    assert str(request.url) == "https://us-east-1.aws.edge.axiom.co/v1/query/_apl?format=tabular"
    assert request.headers["authorization"] == "Bearer xaat-query-test"
    assert json.loads(request.content) == {
        "apl": "['weather-chatbot'] | take 50",
        "startTime": "2026-10-25T12:00:00.000Z",
        "endTime": "2026-11-01T12:00:00.000Z",
    }


def test_rows_come_from_the_first_table_field_by_field() -> None:
    rows = [{"tool": "get_forecast", "calls": 10}, {"tool": "geocode_location", "calls": 12}]
    assert to_rows(to_tabular(rows)) == rows
    second = {"name": "1", "fields": [{"name": "x"}], "columns": [[1]]}
    assert to_rows({"tables": [to_tabular(rows)["tables"][0], second]}) == rows
    # Never Axiom's table of totals, which isn't the query's own.
    totals = {"name": "_totals", "fields": [{"name": "calls"}], "columns": [[22]]}
    assert to_rows({"tables": [totals, to_tabular(rows)["tables"][0]]}) == rows
    assert to_rows({"tables": [totals]}) == []


@pytest.mark.parametrize(
    "body",
    [
        {"tables": []},
        {"tables": [{"fields": [{"name": "x"}]}]},
        {"tables": [{"fields": [{"name": "x"}], "columns": None}]},
        {"tables": [{"fields": [{"name": "x"}], "columns": []}]},
    ],
)
def test_no_table_or_no_columns_is_no_rows(body: object) -> None:
    assert to_rows(body) == []


@pytest.mark.parametrize(
    "body",
    [
        {"tables": [{"fields": [{"name": "x"}, {"name": "y"}], "columns": [[1, 2]]}]},
        {"tables": [{"fields": [{"name": "x"}, {"name": "y"}], "columns": [[1, 2], [3]]}]},
        {"tables": "not a list"},
        {"rows": []},
        ["not", "an", "answer"],
    ],
)
def test_a_table_we_cant_read_is_unreadable(body: object) -> None:
    with pytest.raises(ObservabilityError) as raised:
        to_rows(body)
    assert raised.value.code == "axiom_unreadable"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "axiom_refused"),
        (403, "axiom_refused"),
        (429, "axiom_limited"),
        (400, "axiom_bad_query"),
        (404, "axiom_bad_query"),
        (500, "axiom_unreachable"),
        (503, "axiom_unreachable"),
    ],
)
def test_each_status_axiom_may_answer_with_is_its_own_code_without_axioms_words(status: int, code: str) -> None:
    with pytest.raises(ObservabilityError) as raised:
        ask(AxiomRecordings(status=status))
    assert raised.value.code == code
    for said in (str(raised.value), repr(raised.value), raised.value.user_message):
        assert AXIOM_WORDS not in said
        assert TOKEN.get_secret_value() not in said


def test_an_axiom_out_of_reach_is_unreachable() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host", request=request)

    with pytest.raises(ObservabilityError) as raised:
        ask(httpx2.MockTransport(refuse))
    assert raised.value.code == "axiom_unreachable"


def test_an_axiom_past_its_5_s_is_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(axiom_query, "AXIOM_QUERY_SECONDS", 0.05)

    async def slow(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return httpx2.Response(200, json=to_tabular([]))

    with pytest.raises(ObservabilityError) as raised:
        ask(httpx2.MockTransport(slow))
    assert raised.value.code == "axiom_timeout"


def test_an_answer_that_isnt_json_is_unreadable() -> None:
    with pytest.raises(ObservabilityError) as raised:
        ask(httpx2.MockTransport(lambda request: httpx2.Response(200, text="<html>Gateway</html>")))
    assert raised.value.code == "axiom_unreadable"
