"""
tests/unit/test_sentry.py: the app's errors, to Sentry (step 12): off without its DSN; a line at error sent as the
exception being handled, its class and frames, tagged with where it came from and its ref, never its message, a
request's data, a frame's variables or a breadcrumb; a line at error outside an exception, as its event; a warning,
never. The events are kept by a transport of the tests' own: none leaves.
"""

import json
from collections.abc import Iterator

import pytest
import sentry_sdk
import structlog
from pydantic import SecretStr

from nimbus.config import Settings
from nimbus.logger import configure_logging
from nimbus.sentry import start_sentry, to_sentry_options
from nimbus.utils import to_ref
from tests.fakes import KeptEvents

DSN = "https://public@o0.ingest.sentry.test/0"
REQUEST_ID = "cle1::abcde-1793469547772-79161db8a672"


@pytest.fixture
def sentry(settings: Settings) -> Iterator[KeptEvents]:
    """Sentry, on with the app's own settings and the logging set up, its events kept instead of sent; then off."""
    kept = KeptEvents()
    sentry_sdk.init(**to_sentry_options(settings.model_copy(update={"sentry_dsn": SecretStr(DSN)})), transport=kept)
    configure_logging(settings)
    yield kept
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(None)


def test_without_a_dsn_sentry_stays_off(settings: Settings) -> None:
    assert start_sentry(settings) is False


def test_sentry_hears_only_what_the_app_sends_and_nothing_private(settings: Settings, sentry: KeptEvents) -> None:
    options = to_sentry_options(settings.model_copy(update={"sentry_dsn": SecretStr(DSN)}))
    assert options["dsn"] == DSN
    assert (options["environment"], options["release"]) == ("production", "c7165ac")
    assert options["default_integrations"] is False
    assert options["auto_enabling_integrations"] is False
    assert [type(integration).__name__ for integration in options["integrations"]] == ["DedupeIntegration"]
    assert options["max_breadcrumbs"] == 0
    # As the running client reads them: every category of data off.
    collected = sentry_sdk.get_client().options["data_collection"]
    assert collected["user_info"] is False
    assert collected["stack_frame_variables"] is False
    assert collected["http_bodies"] == []
    assert collected["gen_ai"] == {"inputs": False, "outputs": False}
    assert {collected["cookies"]["mode"], collected["url_query_params"]["mode"]} == {"off"}
    assert collected["http_headers"]["request"]["mode"] == "off"


def test_a_line_at_error_is_its_exception_with_its_frames_and_tags_never_its_words(sentry: KeptEvents) -> None:
    place = "Par" + "is"
    try:
        raise ValueError(f"no forecast for {place}")
    except ValueError:
        with structlog.contextvars.bound_contextvars(requestId=REQUEST_ID):
            structlog.get_logger().error("chat.failed", errorClass="ValueError", lane="rest-no-auth", answerChars=0)
    sentry_sdk.flush()
    [event] = sentry.events
    [exception] = event["exception"]["values"]
    assert exception["type"] == "ValueError"
    assert "value" not in exception
    frames = exception["stacktrace"]["frames"]
    assert frames[-1]["function"] == "test_a_line_at_error_is_its_exception_with_its_frames_and_tags_never_its_words"
    assert not any("vars" in frame for frame in frames)
    assert event["tags"] == {
        "event": "chat.failed",
        "requestId": REQUEST_ID,
        "lane": "rest-no-auth",
        "errorClass": "ValueError",
        "ref": to_ref(REQUEST_ID),
    }
    assert "request" not in event
    assert "user" not in event
    assert not event.get("breadcrumbs", {}).get("values")
    assert place not in json.dumps(event, default=str)


def test_a_line_at_error_outside_an_exception_is_its_event(sentry: KeptEvents) -> None:
    structlog.get_logger().error("chat.failed", errorClass="ConfigError")
    sentry_sdk.flush()
    [event] = sentry.events
    assert event["level"] == "error"
    assert "chat.failed" in json.dumps(event.get("logentry") or event.get("message"))
    assert event["tags"]["errorClass"] == "ConfigError"


def test_a_warning_never_reaches_sentry(sentry: KeptEvents) -> None:
    try:
        raise TimeoutError
    except TimeoutError:
        structlog.get_logger().warning("lane.fallback", errorClass="UpstreamTimeoutError")
    sentry_sdk.flush()
    assert sentry.events == []
