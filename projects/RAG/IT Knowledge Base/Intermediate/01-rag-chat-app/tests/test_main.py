"""
Tests for main.py: the command line; stopping with one clear line and exit code 1, never a traceback, when the
settings, the key or the build fails; answering in the terminal, each answer with the trace ID its log lines carry
in the log file; serving with uvicorn under the app's logging; its app, started the way a host such as Vercel starts
it; and main.py as the only file that runs anything.
"""
import ast
import logging
import os
import re
import subprocess
import sys

import pytest
from fakes import ANSWER, SIZE
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import State
from support import stand_in_engine, write_config

import main
from src.config.settings import PROJECT_DIR, load_settings
from src.exceptions import UpstreamError
from src.observability.trace_store import TraceStore
from src.observability.tracing import trace_context


@pytest.fixture
def config(tmp_path):
    """The shipped settings, with the stand-in embeddings' size and the log file in tmp_path."""
    return write_config(tmp_path, embeddings={"dimensions": SIZE}, logging={"file": str(tmp_path / "app.log")})


@pytest.fixture
def stand_ins(monkeypatch):
    """main() builds an engine on stand-ins, from the settings it loaded."""
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: stand_in_engine(settings))


def run_main(*args: str, **env: str) -> subprocess.CompletedProcess:
    """main.py as its own process, as you'd run it."""
    return subprocess.run([sys.executable, "main.py", *args], cwd=PROJECT_DIR, env={**os.environ, **env},
                          capture_output=True, text=True, timeout=60)


# --- The command line ---

def test_the_default_command_is_serve_and_options_come_first():
    args = main.parse_args([])
    assert (args.command, args.config, args.log_level) == (None, PROJECT_DIR / "config.yaml", None)
    args = main.parse_args(["--log-level", "DEBUG", "ask", "printer", "not", "found"])
    assert (args.command, args.question, args.log_level) == ("ask", ["printer", "not", "found"], "DEBUG")


# --- Stopping clearly ---

def test_without_a_key_it_stops_with_the_message_not_a_traceback():
    # An empty GOOGLE_API_KEY also stops .env from being used: load_dotenv() never overwrites a variable already set
    result = run_main(GOOGLE_API_KEY="")
    assert result.returncode == 1
    assert result.stderr.startswith("Can't start: GOOGLE_API_KEY is not set. Copy .env.example to .env")
    assert "Traceback" not in result.stderr


def test_a_bad_setting_stops_it_with_the_setting_named(tmp_path):
    result = run_main("--config", str(write_config(tmp_path, retrieval={"top_k": 0})), GOOGLE_API_KEY="fake-key")
    assert result.returncode == 1
    assert ("Can't start: Config file has 1 bad setting(s): retrieval.top_k: Input should be greater than or equal "
            "to 1") in result.stderr
    assert "Traceback" not in result.stderr


def test_a_failed_build_stops_it_with_one_error_line(config, monkeypatch, restore_logging, capsys):
    engine = stand_in_engine(load_settings(config))

    def fail():
        raise UpstreamError("embeddings", "GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): "
                                          "400 INVALID_ARGUMENT. API key not valid.")

    monkeypatch.setattr(engine, "build", fail)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    assert main.main(["--config", str(config), "ask"]) == 1
    printed = capsys.readouterr().err
    assert "ERROR   [" in printed and "main: Start-up failed: UPSTREAM_ERROR: embeddings: GoogleGenerativeAIError" \
           in printed
    assert "Traceback" not in printed


# --- Answering in the terminal ---

def test_ask_answers_each_sample_question_with_its_trace_id(config, stand_ins, restore_logging, capsys):
    assert main.main(["--config", str(config), "ask"]) == 0
    printed = capsys.readouterr().out
    questions = load_settings().app.sample_questions
    assert [line for line in printed.splitlines() if line.startswith("Q: ")] == [f"Q: {q}" for q in questions]
    assert printed.startswith(f"Q: {questions[0]}\nA: {ANSWER}\n"
                              "   found by the search: VPN Connection Timeout (VPN, Remote Access), score ")


def test_the_printed_trace_id_finds_the_questions_lines_in_the_log(config, stand_ins, restore_logging, capsys,
                                                                   tmp_path):
    assert main.main(["--config", str(config), "ask", "printer", "not", "found"]) == 0
    printed = capsys.readouterr()
    trace_id = printed.out.split("trace ID: ")[1].split()[0]
    traced = [line.split(": ", 1)[1].split("  ")[0] for line in printed.err.splitlines() if f"[{trace_id}]" in line]
    assert traced == ["embeddings.embed_query ok", "vectordb.search ok", "retrieval.retrieve ok", "prompts.build ok",
                      "llm.generate ok", "pipeline.query ok"]
    build = {line.split("[")[1].split("]")[0] for line in printed.err.splitlines() if "pipeline.build ok" in line}
    assert len(build) == 1 and trace_id not in build          # the build has a trace ID of its own
    assert not (tmp_path / "app.log").exists()                # the log file is the server's: ask writes the console


def test_log_level_debug_adds_the_question_to_the_log(config, stand_ins, restore_logging, capsys):
    main.main(["--config", str(config), "--log-level", "DEBUG", "ask", "printer", "not", "found"])
    assert any(" DEBUG   [" in line and 'Question  question="printer not found"' in line
               for line in capsys.readouterr().err.splitlines())


def test_ctrl_c_during_a_question_stops_ask_with_130(config, monkeypatch, restore_logging, capsys):
    engine = stand_in_engine(load_settings(config))

    def interrupted(question):
        raise KeyboardInterrupt

    monkeypatch.setattr(engine, "query", interrupted)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    assert main.main(["--config", str(config), "ask", "vpn"]) == 130
    assert "Stopped (Ctrl+C)" in capsys.readouterr().err


def test_a_log_file_that_cant_be_opened_stops_the_start_with_one_line(tmp_path, stand_ins, restore_logging, capsys):
    folder = tmp_path / "app.log"
    folder.mkdir()                                            # a folder where the log file should be
    bad = write_config(tmp_path, embeddings={"dimensions": SIZE}, logging={"file": str(folder)})
    assert main.main(["--config", str(bad)]) == 1
    printed = capsys.readouterr().err
    assert printed.startswith("Can't start: the log file can't be opened (") and str(folder) in printed
    assert "Traceback" not in printed


# --- Serving ---

def test_serve_runs_uvicorn_with_the_apps_logging(config, stand_ins, restore_logging, monkeypatch):
    calls = []
    monkeypatch.setattr(main.uvicorn, "run", lambda app, **options: calls.append((app, options)))
    assert main.main(["--config", str(config)]) == 0
    app, options = calls[0]
    assert app.state.engine.stats()["chunks"] == 28                 # built before the server starts
    assert options == {"host": "127.0.0.1", "port": 8000, "log_config": None, "access_log": False}


def test_serve_keeps_traces_and_the_builds_for_good(config, stand_ins, restore_logging, monkeypatch):
    calls = []
    monkeypatch.setattr(main.uvicorn, "run", lambda app, **options: calls.append(app))
    main.main(["--config", str(config)])
    store, engine = calls[0].state.trace_store, calls[0].state.engine
    assert isinstance(store, TraceStore) and store.max_traces == 200
    build = store.get(engine.build_trace_id)["events"]
    assert [event["span"] for event in build if event["span"]][:2] == ["pipeline.create", "pipeline.build"]
    for trace_id in (f"later-{number}" for number in range(201)):      # 201 more traces: the build's stays
        with trace_context(trace_id):
            logging.getLogger("src.test").info("A request")
    assert store.get(engine.build_trace_id) is not None and store.get("later-0") is None


def test_no_trace_store_when_tracing_is_off_or_for_ask(tmp_path, stand_ins, restore_logging, monkeypatch, capsys):
    calls, made = [], []
    monkeypatch.setattr(main.uvicorn, "run", lambda app, **options: calls.append(app))
    off = write_config(tmp_path, embeddings={"dimensions": SIZE}, logging={"file": None}, tracing={"enabled": False})
    main.main(["--config", str(off)])
    assert calls[0].state.trace_store is None
    monkeypatch.setattr(main, "TraceStore", lambda **options: made.append(options))
    on = write_config(tmp_path, embeddings={"dimensions": SIZE}, logging={"file": None})
    assert main.main(["--config", str(on), "ask", "vpn"]) == 0
    assert made == []                                               # ask has no page to show traces on


# --- The app, for a host that imports main.py (Vercel, uvicorn main:app) ---

@pytest.fixture
def host_app(config, stand_ins, restore_logging, monkeypatch):
    """main.app, on the test's settings and stand-ins; its state and title are put back after the test."""
    monkeypatch.setattr(main, "CONFIG_FILE", config)
    monkeypatch.setattr(main.app, "state", State())
    monkeypatch.setattr(main.app, "title", main.app.title)
    return main.app


def test_main_py_has_the_top_level_app_vercel_looks_for():
    # Vercel reads main.py without running it, looking for a top-level `app = ...`; importing it builds nothing
    tree = ast.parse((PROJECT_DIR / "main.py").read_text(encoding="utf-8"))
    assigned = [target.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets
                if isinstance(target, ast.Name)]
    assert "app" in assigned and isinstance(main.app, FastAPI)
    assert not hasattr(main.app.state, "engine")


def test_the_app_builds_its_engine_when_the_host_starts_it(host_app):
    with TestClient(host_app) as client:                       # starts the app, so its lifespan runs, as on Vercel
        assert client.get("/health/ready").json() == {"status": "ready", "chunks": 28}
        info = client.get("/api/v1/info").json()
    assert info["traces"] and host_app.title == info["name"] == load_settings().app.name
    assert host_app.state.trace_store.get(host_app.state.engine.build_trace_id) is not None    # the build's trace


def test_without_a_key_the_hosts_start_fails_with_the_message(host_app, monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    with pytest.raises(main.StartUpError), TestClient(host_app):
        pass
    assert capsys.readouterr().err.startswith("Can't start: GOOGLE_API_KEY is not set.")
    assert not hasattr(host_app.state, "engine")               # it never answers without its engine


def test_on_vercel_the_log_goes_to_the_console_only(config, stand_ins, restore_logging, monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")                          # Vercel sets it; a deployment's files are read-only
    main.start_up(config)
    assert not (tmp_path / "app.log").exists()
    monkeypatch.delenv("VERCEL")
    main.start_up(config)
    assert (tmp_path / "app.log").exists()                     # anywhere else, the log file too


def test_only_main_runs_anything():
    files = [*PROJECT_DIR.glob("*.py"), *(PROJECT_DIR / "src").rglob("*.py"), *(PROJECT_DIR / "tests").glob("*.py")]
    runnable = [path.name for path in files
                if re.search(r"^if __name__ == .__main__.:", path.read_text(encoding="utf-8"), re.MULTILINE)]
    assert runnable == ["main.py"]            # every other file only defines things: main.py wires and runs them
