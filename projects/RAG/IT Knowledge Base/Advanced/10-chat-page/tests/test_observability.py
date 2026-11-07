"""
Tests for observability.py: the request's ID and fields while it's served (and none outside it), a log line in JSON
and in text with its request ID and fields, a secret masked, and setup_logging() called twice keeping one handler.
"""
import json
import logging

from observability import (
    MASK,
    NO_REQUEST,
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    current_request_id,
    note,
    request_context,
    setup_logging,
)


def a_record(message: str = "POST /v1/query 200", **fields) -> logging.LogRecord:
    record = logging.LogRecord("api", logging.INFO, __file__, 1, message, (), None)
    record.__dict__.update(fields)
    RequestIdFilter().filter(record)
    return record


def test_a_request_has_its_id_and_fields_only_while_its_served():
    note(caller="nobody")                               # outside a request: nothing to add to
    with request_context("r1") as fields:
        note(caller="chat-page", status=200)
        inside = current_request_id()
    assert (inside, fields, current_request_id()) == ("r1", {"caller": "chat-page", "status": 200}, NO_REQUEST)


def test_a_line_in_json_has_its_request_id_and_its_fields():
    with request_context("r1"):
        record = a_record(status=200, ms=12.5)
    line = json.loads(JsonFormatter().format(record))
    assert (line["level"], line["logger"], line["request_id"], line["message"], line["status"], line["ms"]) == (
        "INFO", "api", "r1", "POST /v1/query 200", 200, 12.5)
    assert line["time"].endswith("Z")


def test_a_line_in_text_reads_as_one_line():
    with request_context("r1"):
        record = a_record(status=200, caller="chat-page")
    assert TextFormatter().format(record).endswith(' INFO    [r1] api: POST /v1/query 200  status=200 '
                                                   'caller="chat-page"')


def test_a_secret_is_masked_in_every_format():
    record = a_record("calling with AIzaSecretValue")
    assert MASK in JsonFormatter(["AIzaSecretValue"]).format(record)
    assert "AIzaSecretValue" not in TextFormatter(["AIzaSecretValue"]).format(record)


def test_setting_up_twice_keeps_one_handler():
    root = logging.getLogger()
    before = list(root.handlers)
    setup_logging("INFO", "json")
    setup_logging("WARNING", "text")
    added = [handler for handler in root.handlers if handler not in before]
    try:
        assert len(added) == 1 and isinstance(added[0].formatter, TextFormatter)
        assert root.level == logging.WARNING
    finally:
        for handler in added:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)
