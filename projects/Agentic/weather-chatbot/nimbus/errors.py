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


def to_user_message(error: BaseException) -> str:
    """The sentence a visitor sees for an error: its own, if the app expects it, else the fixed one."""
    return error.user_message if isinstance(error, NimbusError) else UNEXPECTED
