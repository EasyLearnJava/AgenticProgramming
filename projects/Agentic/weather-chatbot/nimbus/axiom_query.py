"""
nimbus/axiom_query.py: the Observability pages' questions to Axiom (step 14). One APL query, POSTed to the query door
of Axiom's US edge, where the dataset's organisation is, with a token that can only query, and its time range in the
body; the answer's first table comes back as rows, one dict a row. Axiom refusing the token, its limit reached, out of
reach or past 5 s, refusing the query, or an answer we can't read, is an ObservabilityError, by its code: never with
the token, never with Axiom's own words.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from http import HTTPStatus

import httpx2
from pydantic import BaseModel, SecretStr, ValidationError

from nimbus.constants import AXIOM_QUERY_SECONDS, AXIOM_QUERY_URL
from nimbus.errors import ObservabilityError
from nimbus.utils import to_iso

type Row = dict[str, object]

# What each status Axiom may answer with means for us; any other 4xx, a query it can't run, and a 5xx, an Axiom we
# can't reach.
REFUSED = frozenset({HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN})
# The name Axiom keeps for a table of totals, which isn't the query's own.
TOTALS_TABLE = "_totals"


class AxiomField(BaseModel):
    """A column of a table: its name, as the query's project or summarize names it."""

    name: str


class AxiomTable(BaseModel):
    """A table of the answer: its name, its fields, and its columns, one list a field, in the fields' order."""

    name: str = ""
    fields: list[AxiomField]
    columns: list[list[object]] | None = None


class AxiomAnswer(BaseModel):
    """Axiom's answer in its tabular format: we read its tables, and nothing else."""

    tables: list[AxiomTable]


def to_rows(body: object) -> list[Row]:
    """
    The answer's first table as rows, each row a dict of each field's value; never the table of totals Axiom may add,
    named _totals. No table, or no columns, is no rows; a table whose columns don't match its fields is an answer we
    can't read.
    """
    try:
        answer = AxiomAnswer.model_validate(body)
    except ValidationError:
        raise ObservabilityError("axiom_unreadable") from None
    table = next((table for table in answer.tables if table.name != TOTALS_TABLE), None)
    if table is None:
        return []
    columns = table.columns or []
    if not columns:
        return []
    count = len(columns[0])
    if len(columns) != len(table.fields) or any(len(column) != count for column in columns):
        raise ObservabilityError("axiom_unreadable")
    names = [field.name for field in table.fields]
    return [{name: column[index] for name, column in zip(names, columns, strict=True)} for index in range(count)]


def to_failure(status: int) -> ObservabilityError:
    """What a status other than 200 means: the token refused, Axiom's limit reached, the query refused, or no Axiom."""
    if status in REFUSED:
        return ObservabilityError("axiom_refused")
    if status == HTTPStatus.TOO_MANY_REQUESTS:
        return ObservabilityError("axiom_limited")
    if status < HTTPStatus.INTERNAL_SERVER_ERROR:
        return ObservabilityError("axiom_bad_query")
    return ObservabilityError("axiom_unreachable")


class AxiomQuery:
    """Asks Axiom one query at a time, with the token; each query gets a new HTTP client (the tests give their own)."""

    def __init__(self, token: SecretStr, make_client: Callable[[], httpx2.AsyncClient] = httpx2.AsyncClient) -> None:
        """A way to ask Axiom, with its token."""
        self._token = token
        self._make_client = make_client

    async def run(self, apl: str, start: datetime, end: datetime) -> list[Row]:
        """The query's rows, between the two moments; an ObservabilityError if Axiom can't give them."""
        # ① The query and its time range, in the body; the token in its header, never in a line or an error.
        body = {"apl": apl, "startTime": to_iso(start), "endTime": to_iso(end)}
        headers = {"authorization": f"Bearer {self._token.get_secret_value()}"}
        # ② One POST, within 5 s: past it, or with no answer at all, Axiom is out of reach.
        try:
            async with asyncio.timeout(AXIOM_QUERY_SECONDS), self._make_client() as http:
                response = await http.post(AXIOM_QUERY_URL, json=body, headers=headers)
        except TimeoutError:
            raise ObservabilityError("axiom_timeout") from None
        except httpx2.HTTPError:
            raise ObservabilityError("axiom_unreachable") from None
        # ③ Its status, then its table, as rows.
        if response.status_code != HTTPStatus.OK:
            raise to_failure(response.status_code)
        try:
            answer = response.json()
        except ValueError:
            raise ObservabilityError("axiom_unreadable") from None
        return to_rows(answer)
