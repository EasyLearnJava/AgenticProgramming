"""
tests/unit/test_logger.py: a log line as it reaches stdout: one JSON object, with the build's fields; and another
library's lines: only its warnings and errors, made ours.
"""

import json
import logging

import pytest
import structlog

from nimbus.config import Settings
from nimbus.logger import configure_logging


def test_a_line_is_one_json_object_with_the_builds_fields(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    structlog.get_logger().info("test.line", count=3)
    line = json.loads(capsys.readouterr().out.strip())
    assert line["event"] == "test.line"
    assert line["count"] == 3
    assert line["level"] == "info"
    assert line["env"] == "production"
    assert line["commit"] == "c7165ac"
    assert line["deploymentId"] == "dpl_TestDeployment"
    assert line["ts"].endswith("Z")


def test_a_line_below_the_level_is_not_written(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(_env_file=None, log_level="warning"))
    structlog.get_logger().info("test.quiet")
    assert capsys.readouterr().out == ""


def test_another_library_s_info_line_is_never_written(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    # On Vercel, httpx wrote each request it sent, and google-genai a line of its own, as plain text (issue 43); from
    # step 4, httpx's would hold Open-Meteo's query strings. A library that sets its own logger to info changes nothing
    # (a logger of the test's own, so no real library's is left changed).
    configure_logging(settings)
    chatty = logging.getLogger("tests.chatty_library")
    chatty.setLevel(logging.INFO)
    chatty.info("AFC is enabled with max remote calls: 10.")
    logging.getLogger("httpx").info("HTTP Request: GET https://api.open-meteo.com/v1/forecast?latitude=48.85")
    assert capsys.readouterr().out == ""


def test_another_library_s_warning_is_one_of_our_lines_without_a_query_string(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(settings)
    logging.getLogger("langsmith.client").warning("Failed to send %s: timeout", "https://example.test/runs?id=1")
    line = json.loads(capsys.readouterr().out.strip())
    assert line["event"] == "Failed to send https://example.test/runs?...: timeout"
    assert (line["level"], line["logger"]) == ("warning", "langsmith.client")
    assert (line["env"], line["commit"], line["deploymentId"]) == ("production", "c7165ac", "dpl_TestDeployment")


def test_another_library_s_exception_gives_only_its_class_and_frames(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    # An exception's message can quote what was sent, as a model's error can (step 3); where it went is kept, so a
    # crash a platform logs this way can still be found in the code.
    configure_logging(settings)
    try:
        raise ValueError("https://example.test/?q=a+private+question")
    except ValueError:
        logging.getLogger("google_genai.models").exception("The call failed")
    out = capsys.readouterr().out
    line = json.loads(out.strip())
    assert (line["event"], line["level"], line["exceptionClass"]) == ("The call failed", "error", "ValueError")
    assert line["exceptionFrames"][-1].startswith("unit/test_logger.py:")
    assert "private" not in out


def test_the_root_logger_has_only_our_handler(settings: Settings) -> None:
    # A platform's own handler, put there before the app starts, would write each line a second time, as plain text.
    logging.getLogger().addHandler(logging.StreamHandler())
    configure_logging(settings)
    assert len(logging.getLogger().handlers) == 1
