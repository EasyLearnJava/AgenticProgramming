"""
nimbus/errors.py: the app's own errors and the sentences a visitor sees. The visitor never sees an error's own text,
which can hold anything: an error the app expects has its own sentence; any other gets a fixed one, which the chat
ends with a ref, the end of the request's id, which finds its log lines.
"""

from http import HTTPStatus

from nimbus.constants import QUESTION_MAX_CHARS

# ① What the chat says when a request breaks a rule.
EMPTY_QUESTION = "Please type a question."
QUESTION_TOO_LONG = f"That question is too long: please keep it to {QUESTION_MAX_CHARS:,} characters."
UNREADABLE = "The chat couldn't read that request."
BODY_TOO_LARGE = "That request is too large."
# ② What it says when an answer fails on our side.
UNEXPECTED = "Something went wrong. Please try again."
# ③ What the page says by itself (public/static/chat.js), when no answer can come from us at all.
STOPPED = "Stopped."
CUT_OFF = "The answer was cut off. Please try again."
UNREACHABLE = "The chat couldn't be reached. Please try again."
# The firewall's own 429, which isn't ours, when one address asks too often (step 11): the page says it in our words.
RATE_LIMITED = "Too many questions from here just now. Please wait a minute, then try again."
# ④ What it says when the model can't answer (step 3).
NOT_SET_UP = "The assistant isn't set up on this deployment yet."
MODEL_BUSY = "The assistant is busy right now. Please try again in a minute."
ANSWER_TOO_SLOW = "The assistant took too long to answer. Please try again."
MODEL_FAILED = "The assistant didn't answer. Please try again."
# ⑤ What a weather tool's call says when Open-Meteo can't answer (step 4): the model reads it as the tool's result, and
# the call's chip shows it. And what a chip says when the model called a tool with an input that doesn't fit.
WEATHER_TOO_SLOW = "The weather service took too long to answer. Please try again."
WEATHER_UNREACHABLE = "The weather service can't be reached right now. Please try again in a minute."
WEATHER_BUSY = "The weather service is busy. Please try again in a minute."
WEATHER_UNEXPECTED = "The weather service answered in a way we didn't expect. Please try again later."
TOOL_MISUSED = "The assistant called a weather tool the wrong way."
# ⑥ What the chat says when the conversation the page sends back breaks a rule (step 6).
HISTORY_UNREADABLE = "The chat couldn't read the conversation so far. Please start a new chat."
HISTORY_TOO_LONG = "This conversation is too long to go on. Please start a new chat."
# ⑦ The lanes (step 9): one the form names that isn't open; our own MCP server, which the MCP lane couldn't reach.
LANE_CLOSED = "That lane isn't open yet. Please choose REST · no auth or MCP · no auth."
MCP_UNREACHABLE = "Our MCP server couldn't be reached. Please try again, or choose REST · no auth."
LANE_NEEDS_TOKEN = "That lane needs an Apify token, which this deployment doesn't have. Please choose one with no auth."
# ⑧ Why a forecast on a lane with auth fell back to its twin with no auth (step 10), as its chip says it.
APIFY_TOKEN_REFUSED = "Apify didn't accept our token"
APIFY_CREDIT_USED = "Apify's credit for this month is used up"
APIFY_TOO_SLOW = "Apify took too long"
APIFY_BUSY = "Apify is busy"
APIFY_UNREACHABLE = "Apify can't be reached"
APIFY_UNEXPECTED = "Apify answered in a way we didn't expect"
APIFY_ANSWER_RUNS_USED = "This answer's two Actor runs are used up"
APIFY_DAY_RUNS_USED = "Today's Actor runs are used up"
# ⑨ What an Observability page says when Axiom can't answer it (step 14): no token to ask with, or no answer now.
AXIOM_NOT_CONNECTED = "This deployment can't read Axiom yet: it needs a token that can query its dataset."
AXIOM_UNANSWERED = "Axiom didn't answer just now, so there's nothing to show. Please try again in a minute."


class NimbusError(Exception):
    """An error the app expects: what the visitor is told, the HTTP status, and a short code for the logs."""

    def __init__(self, code: str, user_message: str, status_code: int) -> None:
        """Keeps the three; the error's own text is its code, so a log of it never holds what a visitor typed."""
        super().__init__(code)
        self.code = code
        self.user_message = user_message
        self.status_code = int(status_code)


class InputError(NimbusError):
    """A request that breaks an input rule, found before any work is done: 400, unless said otherwise."""

    def __init__(self, code: str, user_message: str, status_code: int = HTTPStatus.BAD_REQUEST) -> None:
        """The rule's code and sentence, and the status, if not 400."""
        super().__init__(code, user_message, status_code)


class ConfigError(NimbusError):
    """This deployment can't answer: it has no key for the model, or the model refuses the key it has (503)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("model_not_set_up", NOT_SET_UP, HTTPStatus.SERVICE_UNAVAILABLE)


class ModelBusyError(NimbusError):
    """The model turned the call away for now: its quota or its rate (429)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("model_busy", MODEL_BUSY, HTTPStatus.TOO_MANY_REQUESTS)


class AnswerTimeoutError(NimbusError):
    """The answer ran past its time limit, or a call to the model did (504)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("answer_timeout", ANSWER_TOO_SLOW, HTTPStatus.GATEWAY_TIMEOUT)


class ModelFailedError(NimbusError):
    """The model failed in any other way: an error from its API, or a connection that broke (502)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("model_failed", MODEL_FAILED, HTTPStatus.BAD_GATEWAY)


class UpstreamError(NimbusError):
    """Open-Meteo couldn't give a tool its answer (step 4): the tool's call fails with the error's sentence."""


class UpstreamTimeoutError(UpstreamError):
    """Open-Meteo didn't answer in time, on either try (504)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("upstream_timeout", WEATHER_TOO_SLOW, HTTPStatus.GATEWAY_TIMEOUT)


class UpstreamUnavailableError(UpstreamError):
    """Open-Meteo couldn't be reached, or answered with a 5xx, on either try (503)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("upstream_unavailable", WEATHER_UNREACHABLE, HTTPStatus.SERVICE_UNAVAILABLE)


class UpstreamRateLimitedError(UpstreamError):
    """Open-Meteo answered 429, with the wait its Retry-After asked for in seconds, if it gave one (429)."""

    def __init__(self, retry_after_seconds: float | None = None) -> None:
        """The error, with its sentence and the wait asked for."""
        super().__init__("upstream_rate_limited", WEATHER_BUSY, HTTPStatus.TOO_MANY_REQUESTS)
        self.retry_after_seconds = retry_after_seconds


class ContractError(UpstreamError):
    """Open-Meteo's answer wasn't one we can read: another status, no JSON, or not the fields we asked for (502)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("upstream_contract", WEATHER_UNEXPECTED, HTTPStatus.BAD_GATEWAY)


class McpLaneError(UpstreamError):
    """The MCP lane couldn't reach our MCP server, or the server didn't offer our four tools (step 9) (502)."""

    def __init__(self) -> None:
        """The error, with its sentence."""
        super().__init__("mcp_unreachable", MCP_UNREACHABLE, HTTPStatus.BAD_GATEWAY)


class AuthError(UpstreamError):
    """Apify didn't accept our token: 401 or 403 (step 10); the forecast falls back (502)."""

    def __init__(self) -> None:
        """The error, with its sentence, for when nothing can fall back."""
        super().__init__("apify_auth", WEATHER_UNREACHABLE, HTTPStatus.BAD_GATEWAY)


class BudgetExceededError(UpstreamError):
    """Apify asked for payment: our token's credit for the month is used up (402) (step 10); the forecast falls back."""

    def __init__(self) -> None:
        """The error, with its sentence, for when nothing can fall back."""
        super().__init__("apify_budget", WEATHER_UNREACHABLE, HTTPStatus.BAD_GATEWAY)


class RunsUsedUpError(UpstreamError):
    """No Actor run left: 2 an answer, 25 a day (step 10); the forecast falls back with none started (429)."""

    def __init__(self, reason: str) -> None:
        """The error, with whose runs are used up, the answer's or the day's, for the chip."""
        super().__init__("apify_runs_used_up", WEATHER_UNREACHABLE, HTTPStatus.TOO_MANY_REQUESTS)
        self.reason = reason


class ObservabilityError(NimbusError):
    """
    Axiom couldn't answer an Observability page's query (step 14): it refused the token, its limit was reached, it
    couldn't be reached or took too long, it refused the query, or answered in a way we can't read; the code says which
    (502).
    """

    def __init__(self, code: str) -> None:
        """The error, with its code and the page's sentence."""
        super().__init__(code, AXIOM_UNANSWERED, HTTPStatus.BAD_GATEWAY)


def to_user_message(error: BaseException) -> str:
    """The sentence a visitor sees for an error: its own, if the app expects it, else the fixed one."""
    return error.user_message if isinstance(error, NimbusError) else UNEXPECTED
