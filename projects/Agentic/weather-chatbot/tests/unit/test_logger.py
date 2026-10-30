"""tests/unit/test_logger.py: a log line as it reaches stdout: one JSON object, with the build's fields."""

import json

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
