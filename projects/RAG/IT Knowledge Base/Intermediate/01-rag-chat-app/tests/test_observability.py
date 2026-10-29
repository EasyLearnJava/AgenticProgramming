"""
Tests for src/observability: trace IDs (new ones, nesting, and following the work into threads and tasks); spans
(their line when a stage ends, fails or is cancelled, under the layer's logger); setup_logging(): the console's text
line and the file's JSON line, each with its trace ID, the key masked, tracebacks kept, a second call replacing the
first, and the libraries' noise quieted; and the trace store: each line under its trace, in timeline order with its
depth, the newest traces kept (a pinned one always), at most MAX_EVENTS lines each, secrets masked, no tracebacks.
"""
import asyncio
import json
import logging
import re

import pytest
from pydantic import SecretStr

from src.config.settings import load_settings
from src.observability import trace_store as trace_store_module
from src.observability.logging_setup import MASK, setup_logging
from src.observability.trace_store import TraceStore
from src.observability.tracing import NO_TRACE, current_trace_id, new_trace_id, span, trace_context


def logging_settings(**values):
    return load_settings().logging.model_copy(update=values)


# --- Trace IDs ---

def test_a_trace_id_is_16_hex_characters_and_new_each_time():
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(re.fullmatch(r"[0-9a-f]{16}", trace_id) for trace_id in ids)


def test_trace_context_sets_the_id_and_puts_the_old_one_back():
    assert current_trace_id() == NO_TRACE
    with trace_context() as outer:
        assert current_trace_id() == outer
        with trace_context("my-own-id") as inner:
            assert current_trace_id() == inner == "my-own-id"
        assert current_trace_id() == outer
    assert current_trace_id() == NO_TRACE


def test_the_trace_id_follows_the_work_into_threads_and_tasks():
    async def read() -> str:
        return current_trace_id()

    async def work():
        in_thread = await asyncio.to_thread(current_trace_id)       # as the retriever searches the store
        in_task = await asyncio.create_task(read())
        return in_thread, in_task

    with trace_context() as trace_id:
        assert asyncio.run(work()) == (trace_id, trace_id)


# --- Spans ---

def test_a_span_logs_its_stage_duration_and_fields_under_its_layer(logs):
    with trace_context() as trace_id, span("llm.generate", model="a-model") as fields:
        fields["output_tokens"] = 12
    record = logs.find("llm.generate ok")
    assert (record.name, record.levelname, record.trace_id) == ("src.llm", "INFO", trace_id)
    assert (record.span, record.status, record.model, record.output_tokens) == ("llm.generate", "ok", "a-model", 12)
    assert isinstance(record.duration_ms, float)


def test_a_failed_span_logs_the_error_type_and_lets_the_error_go_on(logs):
    with pytest.raises(ValueError), span("vectordb.search", k=5):
        raise ValueError("boom")
    record = logs.find("vectordb.search failed")
    assert (record.levelname, record.status, record.error_type, record.k) == ("WARNING", "failed", "ValueError", 5)


def test_a_cancelled_span_says_so(logs):
    async def slow():
        with span("llm.generate"):
            await asyncio.sleep(10)

    async def run():
        task = asyncio.create_task(slow())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert logs.find("llm.generate cancelled").status == "cancelled"


def test_a_span_stopped_by_ctrl_c_says_cancelled_not_ok(logs):
    with pytest.raises(KeyboardInterrupt), span("embeddings.embed_documents"):
        raise KeyboardInterrupt
    assert "embeddings.embed_documents ok" not in logs.messages()
    assert logs.find("embeddings.embed_documents cancelled").status == "cancelled"


# --- setup_logging() ---

def test_the_console_gets_a_text_line_with_the_trace_id_and_fields(restore_logging, capsys):
    setup_logging(logging_settings(file=None))
    with trace_context("1234567890abcdef"):
        logging.getLogger("src.test").info("Something happened", extra={"chunks": 28, "title": "VPN Timeout"})
    line = capsys.readouterr().err.strip()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z INFO    \[1234567890abcdef\] src.test: "
                        r'Something happened  chunks=28 title="VPN Timeout"', line)


def test_the_file_gets_one_json_object_per_line(restore_logging, tmp_path):
    log_file = tmp_path / "logs" / "app.log"                     # the folder is made if it isn't there
    setup_logging(logging_settings(file=log_file))
    with trace_context("1234567890abcdef"), span("pipeline.query", question_chars=20):
        pass
    logging.getLogger("src.test").info("Outside any trace")
    lines = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["trace_id"] == "1234567890abcdef"
    assert {key: lines[0][key] for key in ("level", "logger", "message", "span", "status", "question_chars")} == {
        "level": "INFO", "logger": "src.pipeline", "message": "pipeline.query ok", "span": "pipeline.query",
        "status": "ok", "question_chars": 20}
    assert lines[1]["trace_id"] == NO_TRACE


def test_json_on_the_console_too_when_asked(restore_logging, capsys):
    setup_logging(logging_settings(file=None, console_format="json"))
    logging.getLogger("src.test").warning("Careful")
    assert json.loads(capsys.readouterr().err)["message"] == "Careful"


def test_a_traceback_goes_into_both_outputs(restore_logging, tmp_path, capsys):
    log_file = tmp_path / "app.log"
    setup_logging(logging_settings(file=log_file))
    try:
        raise RuntimeError("the cause")
    except RuntimeError:
        logging.getLogger("src.test").exception("It failed")
    assert "Traceback (most recent call last)" in capsys.readouterr().err
    entry = json.loads(log_file.read_text(encoding="utf-8"))
    assert "RuntimeError: the cause" in entry["exception"]


def test_the_key_is_masked_wherever_it_appears(restore_logging, tmp_path, capsys):
    log_file = tmp_path / "app.log"
    setup_logging(logging_settings(file=log_file), secrets=[SecretStr("AIzaFakeKey123")])
    logging.getLogger("src.test").error("Bad request to ...?key=AIzaFakeKey123", extra={"url": "x?key=AIzaFakeKey123"})
    printed, written = capsys.readouterr().err, log_file.read_text(encoding="utf-8")
    assert "AIzaFakeKey123" not in printed and "AIzaFakeKey123" not in written
    assert printed.count(MASK) == 2 and written.count(MASK) == 2


def test_a_second_call_replaces_the_first_and_leaves_other_handlers(restore_logging, capsys, logs):
    setup_logging(logging_settings(file=None))
    setup_logging(logging_settings(file=None))
    logging.getLogger("src.test").info("Once")
    assert capsys.readouterr().err.count("Once") == 1           # not twice
    assert "Once" in logs.messages()                            # the test's own handler still gets it


def test_the_level_and_the_quieted_libraries(restore_logging, capsys):
    setup_logging(logging_settings(file=None, level="WARNING"))
    logging.getLogger("src.test").info("Not shown at WARNING")
    setup_logging(logging_settings(file=None, level="DEBUG"))
    logging.getLogger("httpx").info("HTTP Request: POST https://example.com")
    logging.getLogger("google_genai.models").info("AFC is enabled with max remote calls: 10.")
    logging.getLogger("google_genai.models").warning("Something else from Google")
    printed = capsys.readouterr().err
    assert "Not shown" not in printed and "HTTP Request" not in printed and "AFC" not in printed
    assert "Something else from Google" in printed


# --- The trace store ---

@pytest.fixture
def store_logger():
    """A trace store on the app's loggers (src, and so every src.<layer>) and a library's (httpx), and nowhere else;
    with a logger of each kind to write test lines with."""
    store = TraceStore(max_traces=3, secrets=[SecretStr("AIzaFakeKey123")])
    parents = [logging.getLogger("src"), logging.getLogger("httpx")]
    for parent in parents:
        parent.addHandler(store)
        parent.setLevel(logging.DEBUG)
        parent.propagate = False               # the test's lines stop here, at the store
    yield store, logging.getLogger("src.tracetest"), logging.getLogger("httpx.tracetest")
    for parent in parents:
        parent.removeHandler(store)
        parent.setLevel(logging.NOTSET)
        parent.propagate = True


def test_the_store_files_each_line_under_its_trace(store_logger):
    store, app_logger, _ = store_logger
    with trace_context("first"):
        app_logger.info("One")
    with trace_context("second"):
        app_logger.info("Two")
    app_logger.info("Outside any trace")
    with trace_context("page-file", recorded=False):
        app_logger.info("Not recorded")
    assert [event["message"] for event in store.get("first")["events"]] == ["One"]
    assert [event["message"] for event in store.get("second")["events"]] == ["Two"]
    assert store.get("page-file") is None


def test_the_store_keeps_the_apps_debug_lines_and_the_libraries_from_info(store_logger):
    store, app_logger, library_logger = store_logger
    with trace_context("t"):
        app_logger.debug("The app's detail")
        library_logger.debug("A library's chatter")
        library_logger.info("HTTP Request: POST https://example.com")
    assert [event["message"] for event in store.get("t")["events"]] == ["The app's detail",
                                                                         "HTTP Request: POST https://example.com"]


def test_a_traces_events_are_in_timeline_order_each_with_its_depth(store_logger):
    store, app_logger, _ = store_logger
    with trace_context("t"):
        app_logger.info("Before")
        with span("pipeline.query"):
            app_logger.debug("Inside the query")
            with span("retrieval.retrieve", k=5):
                app_logger.debug("Inside the retrieval")
    events = store.get("t")["events"]
    assert [(event["message"], event["depth"]) for event in events] == [
        ("Before", 0), ("pipeline.query ok", 0), ("Inside the query", 1), ("retrieval.retrieve ok", 1),
        ("Inside the retrieval", 2)]
    query, retrieve = events[1], events[3]
    assert (query["span"], query["status"], retrieve["fields"]) == ("pipeline.query", "ok", {"k": 5})
    assert query["at_ms"] <= retrieve["at_ms"]                               # a span is placed where it started
    assert retrieve["at_ms"] + retrieve["duration_ms"] <= query["at_ms"] + query["duration_ms"] + 0.2
    assert query["logged_ms"] >= retrieve["logged_ms"]                       # and written where it ended


def test_the_newest_traces_are_kept_and_a_pinned_one_always(store_logger):
    store, app_logger, _ = store_logger                       # max_traces=3
    store.pin("build")
    for trace_id in ("build", "t1", "t2", "t3", "t4"):
        with trace_context(trace_id):
            app_logger.info("A line")
    assert [trace_id for trace_id in ("build", "t1", "t2", "t3", "t4") if store.get(trace_id)] == ["build", "t3", "t4"]


def test_a_trace_keeps_at_most_max_events_and_counts_the_rest(store_logger, monkeypatch):
    store, app_logger, _ = store_logger
    monkeypatch.setattr(trace_store_module, "MAX_EVENTS", 3)
    with trace_context("t"):
        for number in range(5):
            app_logger.info("Line %d", number)
    kept = store.get("t")
    assert ([event["message"] for event in kept["events"]], kept["dropped"]) == (["Line 0", "Line 1", "Line 2"], 2)


def test_a_traces_events_mask_the_key_and_carry_no_traceback(store_logger):
    store, app_logger, _ = store_logger
    with trace_context("t"):
        try:
            raise RuntimeError("refused key AIzaFakeKey123")
        except RuntimeError:
            app_logger.exception("Failed with AIzaFakeKey123", extra={"url": "x?key=AIzaFakeKey123"})
    event = store.get("t")["events"][0]
    assert "AIzaFakeKey123" not in json.dumps(event) and "Traceback" not in json.dumps(event)
    assert (event["message"], event["fields"]["url"], event["error"]) == (
        f"Failed with {MASK}", f"x?key={MASK}", f"RuntimeError: refused key {MASK}")


def test_with_a_trace_store_the_outputs_keep_their_level_and_the_store_gets_more(restore_logging, capsys):
    store = TraceStore(max_traces=10)
    setup_logging(logging_settings(file=None, level="INFO"), trace_store=store)
    with trace_context("t"):
        logging.getLogger("src.test").debug("The question's text")
        logging.getLogger("httpx").info("HTTP Request: POST https://example.com")
        logging.getLogger("src.test").info("Shown everywhere")
    printed = capsys.readouterr().err
    assert "Shown everywhere" in printed and "question's text" not in printed and "HTTP Request" not in printed
    assert [event["message"] for event in store.get("t")["events"]] == [
        "The question's text", "HTTP Request: POST https://example.com", "Shown everywhere"]
