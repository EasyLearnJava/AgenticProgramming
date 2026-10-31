"""
nimbus/apify.py: Apify, the lanes with auth's way to the Actor (step 10). Over REST, one request runs the Actor and
answers with its items: POST run-sync-get-dataset-items, its build, 18 s and $0.01 pinned in the address. Over MCP,
Apify's MCP server, which speaks MCP's 2025 version, with sessions: the handshake and its tools within 5 s, our pin
checked, then, for a forecast, two messages: call-actor, which runs the Actor with the same three limits, and
get-dataset-items, which reads its items. The token goes only in a header, never in an address or a log line, and a
chip shows it masked. Each failure is one of our errors: a token refused, AuthError; a credit used up,
BudgetExceededError; a run too slow, UpstreamTimeoutError; Apify busy, UpstreamRateLimitedError; Apify failing or out of
reach, UpstreamUnavailableError; anything else, ContractError. Nothing is retried: each run costs.
"""

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode, urlsplit

import httpx2
import structlog
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, TextContent, Tool
from pydantic import BaseModel, SecretStr, ValidationError

from nimbus.constants import (
    ACTOR_TOOL_NAME,
    APIFY_ACTOR,
    APIFY_ACTOR_BUILD,
    APIFY_ACTOR_RUN_URL,
    APIFY_DATASET_TOOL,
    APIFY_MAX_CHARGE_USD,
    APIFY_MCP_CONNECT_SECONDS,
    APIFY_MCP_URL,
    APIFY_ME_URL,
    APIFY_RUN_TIMEOUT_SECONDS,
    APIFY_RUN_TOOL,
    AUTH_TOOL_SECONDS,
    MAX_ACTOR_ITEMS,
    MAX_APIFY_DETAIL_CHARS,
)
from nimbus.errors import (
    AuthError,
    BudgetExceededError,
    ContractError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nimbus.mcp_lane import find_call, to_leaves, to_wire_request, unwrap
from nimbus.open_meteo import WireRequest
from nimbus.utils import to_ms

log = structlog.get_logger()

MASKED_AUTHORIZATION: Final = "Bearer <APIFY_TOKEN>"
APIFY_HOST: Final = urlsplit(APIFY_ACTOR_RUN_URL).netloc
APIFY_MCP_HOST: Final = urlsplit(APIFY_MCP_URL).netloc
# call-actor's input as we rely on it: the Actor, its input, the wait, and the three limits; the Actor's own input.
RUN_FIELDS: Final = (
    "actor",
    "input",
    "waitSecs",
    "callOptions.build",
    "callOptions.timeout",
    "callOptions.maxTotalChargeUsd",
)
ACTOR_FIELDS: Final = ("locations", "forecastDays", "mode")
# An error result's words that mean the account can't pay: Apify's MCP server doesn't document them (our reading).
PAYMENT_WORDS: Final = re.compile(r"payment|credit|usage limit|not enough usage", re.IGNORECASE)
STILL_RUNNING: Final = frozenset({"READY", "RUNNING", "TIMING-OUT", "TIMED-OUT"})
HTTP_OK: Final = 200
HTTP_CREATED: Final = 201
HTTP_BAD_REQUEST: Final = 400
ACCOUNT_STATUSES: Final = frozenset({401, 402, 403})


@dataclass(frozen=True)
class ActorRun:
    """One run's items, and the request that ran it, as a chip shows it."""

    items: list[Any]
    request: WireRequest


def make_apify_http_client() -> httpx2.AsyncClient:
    """
    A new HTTP client, for one answer's calls to Apify: an Actor's run takes seconds, so each wait has the call's 20 s.
    The app keeps this factory in its state, and the tests give it one that plays Apify back.
    """
    return httpx2.AsyncClient(timeout=httpx2.Timeout(AUTH_TOOL_SECONDS))


def to_limits() -> dict[str, Any]:
    """The Actor's limits, the same on both doors: its build, its run's time, and its charge."""
    return {"build": APIFY_ACTOR_BUILD, "timeout": APIFY_RUN_TIMEOUT_SECONDS, "maxTotalChargeUsd": APIFY_MAX_CHARGE_USD}


def to_run_url() -> str:
    """The REST door's address: the Actor's run-sync, the three limits in its query."""
    return f"{APIFY_ACTOR_RUN_URL}?{urlencode(to_limits())}"


def to_rest_request(actor_input: dict[str, Any]) -> WireRequest:
    """The REST door's request, as a chip shows it: the token masked."""
    headers = {"authorization": MASKED_AUTHORIZATION, "content-type": "application/json"}
    return WireRequest(method="POST", url=to_run_url(), headers=headers, body=json.dumps(actor_input, indent=2))


def to_run_arguments(actor_input: dict[str, Any]) -> dict[str, Any]:
    """call-actor's arguments: the Actor, its input, and the REST door's three limits; its wait, the run's 18 s."""
    return {
        "actor": APIFY_ACTOR,
        "input": actor_input,
        "waitSecs": APIFY_RUN_TIMEOUT_SECONDS,
        "callOptions": to_limits(),
    }


def to_call_actor_example(actor_input: dict[str, Any]) -> WireRequest:
    """The MCP door's first message, for the compare view: the token masked; the SDK's client adds its own headers."""
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
    message["params"] = {"name": APIFY_RUN_TOOL, "arguments": to_run_arguments(actor_input)}
    headers = {"authorization": MASKED_AUTHORIZATION, "content-type": "application/json"}
    return WireRequest(method="POST", url=APIFY_MCP_URL, headers=headers, body=json.dumps(message, indent=2))


def to_status_error(status: int) -> UpstreamError:
    """An error status of Apify's as one of our errors."""
    errors: dict[int, Callable[[], UpstreamError]] = {
        401: AuthError,
        402: BudgetExceededError,
        403: AuthError,
        408: UpstreamTimeoutError,
        429: UpstreamRateLimitedError,
    }
    if status in errors:
        return errors[status]()
    return UpstreamUnavailableError() if status >= 500 else ContractError()


def to_apify_detail(response: httpx2.Response) -> str:
    """
    Apify's own words about a failed run: its error's type; and its message only for an account's problem, since other
    messages can quote the input.
    """
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    kind = error.get("type") if isinstance(error, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    words = [kind if isinstance(kind, str) else "no error type"]
    if response.status_code in ACCOUNT_STATUSES and isinstance(message, str):
        words.append(f"({message})")
    return " ".join(words)[:MAX_APIFY_DETAIL_CHARS]


async def run_actor_rest(http: httpx2.AsyncClient, token: SecretStr, actor_input: dict[str, Any]) -> ActorRun:
    """
    One run over Apify's REST API, which answers with the run's items: the token in a header; one upstream.http line,
    with Apify's own words for a failure.
    """
    fields = {"upstream": "apify", "host": APIFY_HOST, "path": urlsplit(APIFY_ACTOR_RUN_URL).path}
    started = time.perf_counter()
    try:
        authorization = {"authorization": f"Bearer {token.get_secret_value()}"}
        response = await http.post(to_run_url(), json=actor_input, headers=authorization)
    except httpx2.HTTPError as error:
        failure: UpstreamError = (
            UpstreamTimeoutError() if isinstance(error, httpx2.TimeoutException) else UpstreamUnavailableError()
        )
        ms = to_ms(time.perf_counter() - started)
        log.info("upstream.http", **fields, status="failed", ms=ms, errorClass=type(failure).__name__)
        raise failure from error
    ms = to_ms(time.perf_counter() - started)
    if response.status_code not in (HTTP_OK, HTTP_CREATED):
        failure = to_status_error(response.status_code)
        detail = to_apify_detail(response)
        failed = {"httpStatus": response.status_code, "errorClass": type(failure).__name__, "apifyError": detail}
        log.info("upstream.http", **fields, status="failed", ms=ms, **failed)
        raise failure
    try:
        items = response.json()
    except ValueError as error:
        raise ContractError from error
    if not isinstance(items, list):
        raise ContractError
    log.info("upstream.http", **fields, status="ok", httpStatus=response.status_code, ms=ms, items=len(items))
    return ActorRun(items, to_rest_request(actor_input))


async def check_apify_token(http: httpx2.AsyncClient, token: SecretStr) -> None:
    """
    The health check's call to Apify's REST API (step 12): the account behind the token, read, which runs nothing; a
    token Apify refuses is AuthError. Nothing it answers is kept but its status; one upstream.http line.
    """
    fields = {"upstream": "apify", "host": APIFY_HOST, "path": urlsplit(APIFY_ME_URL).path}
    started = time.perf_counter()
    try:
        response = await http.get(APIFY_ME_URL, headers={"authorization": f"Bearer {token.get_secret_value()}"})
    except httpx2.HTTPError as error:
        failure: UpstreamError = (
            UpstreamTimeoutError() if isinstance(error, httpx2.TimeoutException) else UpstreamUnavailableError()
        )
        ms = to_ms(time.perf_counter() - started)
        log.info("upstream.http", **fields, status="failed", ms=ms, errorClass=type(failure).__name__)
        raise failure from error
    ms = to_ms(time.perf_counter() - started)
    if response.status_code != HTTP_OK:
        failure = to_status_error(response.status_code)
        failed = {"httpStatus": response.status_code, "errorClass": type(failure).__name__}
        log.info("upstream.http", **fields, status="failed", ms=ms, **failed)
        raise failure
    log.info("upstream.http", **fields, status="ok", httpStatus=response.status_code, ms=ms)


def _resolve(root: dict[str, Any], node: Any) -> Any:
    """A schema as it is, through a $ref to the root's $defs, or the first of its anyOf with properties."""
    while isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            node = root.get("$defs", {}).get(reference.removeprefix("#/$defs/"))
            continue
        options = node.get("anyOf")
        if "properties" not in node and isinstance(options, list):
            node = next(
                (
                    option
                    for option in options
                    if isinstance(_resolve(root, option), dict) and "properties" in _resolve(root, option)
                ),
                None,
            )
            continue
        return node
    return node


def has_field(schema: Any, path: str) -> bool:
    """Whether a tool's input schema has the field at the path, "callOptions.build" say."""
    root = schema if isinstance(schema, dict) else {}
    node: Any = root
    for name in path.split("."):
        node = _resolve(root, node)
        properties = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(properties, dict) or name not in properties:
            return False
        node = properties[name]
    return True


def check_pin(tools: list[Tool]) -> None:
    """
    Apify's tools, as we rely on them: call-actor, taking the Actor, its input, its wait and the three limits; the
    Actor's own tool, with its input's three fields; and get-dataset-items. Apify's server drops a field it doesn't
    know without a word, so one missing is a ContractError, and the lane falls back.
    """
    by_name = {tool.name: tool for tool in tools}
    run, actor = by_name.get(APIFY_RUN_TOOL), by_name.get(ACTOR_TOOL_NAME)
    if run is None or actor is None or APIFY_DATASET_TOOL not in by_name:
        raise ContractError
    pinned = all(has_field(run.input_schema, f) for f in RUN_FIELDS) and all(
        has_field(actor.input_schema, f) for f in ACTOR_FIELDS
    )
    if not pinned:
        raise ContractError


def to_apify_error(error: BaseException, statuses: list[int]) -> UpstreamError:
    """
    An exchange with Apify's MCP server that failed, as one of our errors: by the last error status its HTTP client
    saw, since the SDK keeps none; else past its time, UpstreamTimeoutError; else UpstreamUnavailableError.
    """
    status = next((status for status in reversed(statuses) if status >= HTTP_BAD_REQUEST), None)
    if status is not None:
        return to_status_error(status)
    leaves = to_leaves(error) if isinstance(error, BaseExceptionGroup) else [error]
    if any(isinstance(leaf, (TimeoutError, httpx2.TimeoutException)) for leaf in leaves):
        return UpstreamTimeoutError()
    return UpstreamUnavailableError()


class _RunAnswer(BaseModel):
    """call-actor's answer: the run's status and its storages' ids, not its items."""

    status: str
    storages: dict[str, Any]


class _ItemsAnswer(BaseModel):
    """get-dataset-items' answer: the items, and how many the dataset holds."""

    items: list[Any]
    totalItemCount: int | None = None  # noqa: N815 - Apify's own name


def _answer_of(result: CallToolResult) -> Any:
    """A tool's answer: its structured content, or its first text if that's JSON."""
    if result.structured_content is not None:
        return result.structured_content
    text = next((block.text for block in result.content if isinstance(block, TextContent)), "")
    try:
        return json.loads(text)
    except ValueError:
        return None


def to_dataset_id(answer: Any) -> str:
    """
    The run's dataset, if it succeeded: still running after its 18 s, UpstreamTimeoutError; ended any other way,
    UpstreamUnavailableError.
    """
    try:
        run = _RunAnswer.model_validate(answer)
        dataset_id = run.storages["datasets"]["default"]["id"]
    except (ValidationError, KeyError, TypeError) as error:
        raise ContractError from error
    if run.status in STILL_RUNNING:
        raise UpstreamTimeoutError
    if run.status != "SUCCEEDED" or not isinstance(dataset_id, str):
        raise UpstreamUnavailableError
    return dataset_id


def to_items(answer: Any) -> list[Any]:
    """The dataset's items, all of them in one read, or a ContractError."""
    try:
        read = _ItemsAnswer.model_validate(answer)
    except ValidationError as error:
        raise ContractError from error
    if read.totalItemCount is not None and read.totalItemCount > len(read.items):
        raise ContractError
    return read.items


@dataclass
class ApifyMcp:
    """A connection to Apify's MCP server for one answer, or the error that kept it from opening."""

    client: Client | None
    sent: list[httpx2.Request]
    statuses: list[int]
    error: UpstreamError | None = None

    async def run_actor(self, actor_input: dict[str, Any]) -> ActorRun:
        """One run through call-actor, then its items through get-dataset-items; the chip gets call-actor's request."""
        if self.client is None:
            raise self.error or UpstreamUnavailableError()
        arguments = to_run_arguments(actor_input)
        dataset_id = to_dataset_id(await self._call(self.client, APIFY_RUN_TOOL, arguments))
        read = await self._call(self.client, APIFY_DATASET_TOOL, {"datasetId": dataset_id, "limit": MAX_ACTOR_ITEMS})
        items = to_items(read)
        request = find_call(self.sent, APIFY_RUN_TOOL, arguments)
        if request is None:
            raise ContractError
        return ActorRun(items, to_wire_request(request))

    async def _call(self, client: Client, tool: str, arguments: dict[str, Any]) -> Any:
        """One tools/call to Apify's server, and its upstream.mcp line; an error result's words are never kept."""
        fields = {"upstream": "apify", "host": APIFY_MCP_HOST, "tool": tool}
        self.statuses.clear()
        started = time.perf_counter()
        try:
            result = await client.call_tool(tool, arguments)
        except Exception as error:
            failure = to_apify_error(error, self.statuses)
            ms = to_ms(time.perf_counter() - started)
            log.info("upstream.mcp", **fields, status="failed", ms=ms, errorClass=type(failure).__name__)
            raise failure from error
        ms = to_ms(time.perf_counter() - started)
        if result.is_error:
            text = next((block.text for block in result.content if isinstance(block, TextContent)), "")
            failure = BudgetExceededError() if PAYMENT_WORDS.search(text) else ContractError()
            log.info("upstream.mcp", **fields, status="failed", ms=ms, errorClass=type(failure).__name__)
            raise failure
        log.info("upstream.mcp", **fields, status="ok", ms=ms)
        return _answer_of(result)


@asynccontextmanager
async def open_apify_mcp(http_client: httpx2.AsyncClient, token: SecretStr) -> AsyncIterator[ApifyMcp]:
    """
    A connection to Apify's MCP server for one answer, opened with the lane: an anyio task group must be left by the
    task that entered it, and tool calls run in tasks of their own. The 2025 handshake and the tool list within 5 s,
    our pin checked; one that fails gives a connection that holds its error, so the forecast falls back. The session is
    left to expire: its DELETE would have no time limit. Each request and each POST's status is kept.
    """
    sent: list[httpx2.Request] = []
    statuses: list[int] = []

    async def keep(request: httpx2.Request) -> None:
        """Keeps a request as it goes out."""
        sent.append(request)

    async def keep_status(response: httpx2.Response) -> None:
        """Keeps a POST's status, which the SDK doesn't."""
        if response.request.method == "POST":
            statuses.append(response.status_code)

    hooks = http_client.event_hooks
    http_client.event_hooks = {
        "request": [*hooks.get("request", []), keep],
        "response": [*hooks.get("response", []), keep_status],
    }
    http_client.headers["authorization"] = f"Bearer {token.get_secret_value()}"
    fields = {"upstream": "apify", "host": APIFY_MCP_HOST}
    started = time.perf_counter()
    try:
        async with http_client as http, AsyncExitStack() as stack:
            try:
                async with asyncio.timeout(APIFY_MCP_CONNECT_SECONDS):
                    transport = streamable_http_client(APIFY_MCP_URL, http_client=http, terminate_on_close=False)
                    client = await stack.enter_async_context(Client(transport, mode="legacy"))
                    listed = await client.list_tools()
                check_pin(listed.tools)
                connection = ApifyMcp(client, sent, statuses)
                log.info("lane.connect", **fields, status="ok", ms=to_ms(time.perf_counter() - started))
            except Exception as error:
                failure = error if isinstance(error, ContractError) else to_apify_error(error, statuses)
                connection = ApifyMcp(None, sent, statuses, failure)
                ms = to_ms(time.perf_counter() - started)
                log.warning("lane.connect", **fields, status="failed", ms=ms, errorClass=type(failure).__name__)
            yield connection
    except BaseExceptionGroup as group:
        inner = unwrap(group)
        raise inner from inner.__cause__
