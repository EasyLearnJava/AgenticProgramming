"""
Tests for main.py: the command line; stopping with one clear line and exit code 1, never a traceback, when the
settings, the key or the build fails; answering in the terminal, each answer with the trace ID its log lines carry
in the log file; serving with uvicorn under the app's logging; its app, started the way a host such as Vercel starts
it, and started anyway when a model provider fails, building at a later question; index, which saves the vectors a
later start loads (and exits 1 when it fails, or with --best-effort only warns when a provider fails, so Vercel's
deployment goes ahead), and vercel.json, whose build runs it unless it can tell nothing in this folder changed, run in
real git repos; and main.py as the only file that runs anything.
"""
import ast
import json
import logging
import os
import re
import shutil
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
from src.exceptions import UpstreamDailyQuotaError, UpstreamError, UpstreamRateLimitError
from src.observability.trace_store import TraceStore
from src.observability.tracing import trace_context
from src.pipeline import rag_engine


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
    assert main.parse_args(["--log-level", "DEBUG", "index"]).command == "index"
    assert main.parse_args(["index", "--best-effort"]).best_effort and not main.parse_args(["index"]).best_effort


# --- Stopping clearly ---

@pytest.mark.parametrize("command", [[], ["index"]], ids=["serve", "index"])
def test_without_a_key_it_stops_with_the_message_not_a_traceback(command):
    # An empty GOOGLE_API_KEY also stops .env from being used: load_dotenv() never overwrites a variable already set
    result = run_main(*command, GOOGLE_API_KEY="")
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


def test_when_a_provider_fails_at_the_hosts_start_it_serves_anyway_and_builds_at_a_later_question(
        host_app, config, monkeypatch, capsys):
    engine = stand_in_engine(load_settings(config))
    embed = engine.embedder.embed_documents

    def used_up(texts):
        raise UpstreamDailyQuotaError("embeddings", "429 RESOURCE_EXHAUSTED: Embed content requests per day")

    monkeypatch.setattr(engine.embedder, "embed_documents", used_up)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    question = {"question": "My VPN keeps timing out"}
    with TestClient(host_app) as client:                       # the start doesn't fail: the page can say why
        assert (client.get("/").status_code, client.get("/health/live").status_code) == (200, 200)
        assert client.get("/health/ready").json()["error"]["code"] == "NOT_READY"
        refused = client.post("/api/v1/query", json=question)
        assert (refused.status_code, refused.json()["error"]["message"]) == (
            503, "The AI service's quota for today is used up. Try again after midnight Pacific time.")
        assert client.get("/api/v1/info").json()["error"]["code"] == "UPSTREAM_DAILY_QUOTA"
        monkeypatch.setattr(engine.embedder, "embed_documents", embed)       # the quota is back
        assert client.post("/api/v1/query", json=question).status_code == 503  # within the minute: not asked again
        monkeypatch.setattr(rag_engine, "REBUILD_SECONDS", 0.0)              # the minute is over
        assert client.post("/api/v1/query", json=question).json()["answer"] == ANSWER
        assert client.get("/health/ready").json() == {"status": "ready", "chunks": 28}
    printed = capsys.readouterr().err
    assert "main: Start-up couldn't build the knowledge base: UPSTREAM_DAILY_QUOTA" in printed
    assert "Traceback" not in printed


def test_ask_still_stops_when_a_provider_fails_at_the_start(config, monkeypatch, restore_logging, capsys):
    engine = stand_in_engine(load_settings(config))

    def used_up(texts):
        raise UpstreamDailyQuotaError("embeddings", "429 RESOURCE_EXHAUSTED: Embed content requests per day")

    monkeypatch.setattr(engine.embedder, "embed_documents", used_up)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    assert main.main(["--config", str(config), "ask", "vpn"]) == 1     # a terminal has no later question
    assert "main: Start-up failed: UPSTREAM_DAILY_QUOTA" in capsys.readouterr().err


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


# --- Saving the vectors once: index, and Vercel's build ---

def test_index_saves_the_vectors_and_the_next_start_embeds_nothing(config, stand_ins, restore_logging, capsys,
                                                                    tmp_path):
    assert main.main(["--config", str(config), "index"]) == 0
    indexed = capsys.readouterr().err
    assert "embeddings.embed_documents ok" in indexed and "main: Vectors saved: each start-up loads them" in indexed
    assert (tmp_path / "data" / "vectors.json").exists()      # vector_file: data/vectors.json, next to the config
    assert not (tmp_path / "app.log").exists()                # index logs to the console only
    assert main.main(["--config", str(config), "ask", "vpn"]) == 0
    started = capsys.readouterr().err
    assert "embeddings.load_vectors ok" in started and "used=True vectors=28" in started
    assert "embeddings.embed_documents" not in started        # the start embedded nothing: no call to the model


def test_a_failed_index_exits_1_so_vercels_build_stops(config, monkeypatch, restore_logging, capsys, tmp_path):
    engine = stand_in_engine(load_settings(config))

    def busy(texts):
        raise UpstreamRateLimitError("embeddings", "GoogleGenerativeAIError: 429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(engine.embedder, "embed_documents", busy)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    assert main.main(["--config", str(config), "index"]) == 1
    printed = capsys.readouterr().err
    assert "main: Indexing failed: UPSTREAM_RATE_LIMITED: embeddings: GoogleGenerativeAIError: 429" in printed
    assert "Traceback" not in printed
    assert not (tmp_path / "data" / "vectors.json").exists()  # nothing saved: a start-up embeds instead


def test_ctrl_c_stops_index_with_130(config, monkeypatch, restore_logging, capsys):
    engine = stand_in_engine(load_settings(config))

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(engine, "index", interrupted)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    assert main.main(["--config", str(config), "index"]) == 130
    assert "Indexing stopped (Ctrl+C)" in capsys.readouterr().err
    monkeypatch.setattr(main, "load_settings", interrupted)   # before logging is set up, too: no traceback
    assert main.main(["--config", str(config), "index"]) == 130


def test_on_vercel_a_start_with_no_saved_vectors_warns(config, stand_ins, restore_logging, monkeypatch, capsys):
    monkeypatch.setenv("VERCEL", "1")
    main.start_up(config)
    assert "main: No saved vectors on Vercel (" in capsys.readouterr().err     # each instance would embed the chunks
    assert main.main(["--config", str(config), "index"]) == 0
    capsys.readouterr()
    main.start_up(config)
    assert "No saved vectors" not in capsys.readouterr().err


def test_vercels_build_runs_index_and_a_providers_failure_doesnt_stop_the_deployment():
    # vercel.json, in the folder Vercel deploys: its build command runs after the packages are installed
    settings = json.loads((PROJECT_DIR / "vercel.json").read_text(encoding="utf-8"))
    assert settings["buildCommand"] == "python main.py index --best-effort"


SHELL = shutil.which("sh") or shutil.which("bash")
# The last deployment's commit, as Vercel gave it after more commits than its clone holds: git calls it a bad object
NOT_CLONED = "ef143e7efc3d6e0376a97cb68fe596d3649abd7b"


@pytest.mark.skipif(SHELL is None, reason="runs vercel.json's ignore command, which needs a POSIX shell, as Vercel's "
                                          "build has (on Windows: Git Bash's sh)")
@pytest.mark.parametrize("previous, changed_here, expected", [
    ("parent", False, 0),          # nothing in this folder changed since the last deployment: the build is skipped
    ("parent", True, 1),           # it changed: build
    ("not cloned", False, 1),      # Vercel's clone doesn't hold the last deployment's commit, so it can't tell: build
    ("same", False, 1),            # a redeploy of the deployment's own commit: build
    ("none", False, 1),            # no deployment yet: build
], ids=["unchanged", "changed", "commit not in the clone", "redeploy", "first deploy"])
def test_vercels_ignore_command_skips_a_build_only_when_it_can_tell_nothing_here_changed(tmp_path, previous,
                                                                                         changed_here, expected):
    # The ignore command runs before the build, in this folder: exit 0 skips the build, anything else builds. Here it
    # runs in a real git repo: an app folder, and another project's file beside it
    ignore = json.loads((PROJECT_DIR / "vercel.json").read_text(encoding="utf-8"))["ignoreCommand"]
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)

    def git(*args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args], cwd=repo,
                              check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    (repo / "app" / "main.py").write_text("v1", encoding="utf-8")
    (repo / "other.txt").write_text("v1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "the last deployment")
    deployed = git("rev-parse", "HEAD")
    (repo / ("app/main.py" if changed_here else "other.txt")).write_text("v2", encoding="utf-8")
    git("commit", "-qam", "the push")
    pushed = git("rev-parse", "HEAD")
    env = {**os.environ, "VERCEL_GIT_COMMIT_SHA": pushed,
           "VERCEL_GIT_PREVIOUS_SHA": {"parent": deployed, "not cloned": NOT_CLONED, "same": pushed,
                                       "none": ""}[previous]}
    result = subprocess.run([SHELL, "-c", ignore], cwd=repo / "app", env=env, capture_output=True, text=True)
    assert result.returncode == expected, result.stderr
    assert result.stderr == ""                                 # git's "bad object" isn't printed: it simply builds


def test_with_best_effort_a_providers_failure_only_warns_so_the_deployment_goes_ahead(config, monkeypatch,
                                                                                      restore_logging, capsys,
                                                                                      tmp_path):
    engine = stand_in_engine(load_settings(config))

    def used_up(texts):
        raise UpstreamDailyQuotaError("embeddings", "429 RESOURCE_EXHAUSTED: Embed content requests per day")

    monkeypatch.setattr(engine.embedder, "embed_documents", used_up)
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: engine)
    assert main.main(["--config", str(config), "index", "--best-effort"]) == 0
    printed = capsys.readouterr().err
    assert "main: No vectors saved: UPSTREAM_DAILY_QUOTA: embeddings: 429" in printed and "Traceback" not in printed
    assert not (tmp_path / "data" / "vectors.json").exists()  # nothing saved: each start embeds instead
    assert main.main(["--config", str(config), "index"]) == 1  # without it, the build stops
    # Any other failure still stops the deployment: here, the knowledge base file isn't there
    (tmp_path / "broken").mkdir()
    broken = write_config(tmp_path / "broken", ingestion={"path": str(tmp_path / "missing.csv")},
                          embeddings={"dimensions": SIZE})
    monkeypatch.setattr(main, "create_engine", lambda settings, api_key: stand_in_engine(settings))
    assert main.main(["--config", str(broken), "index", "--best-effort"]) == 1
    assert "main: Indexing failed: INGESTION_ERROR" in capsys.readouterr().err


def test_only_main_runs_anything():
    files = [*PROJECT_DIR.glob("*.py"), *(PROJECT_DIR / "src").rglob("*.py"), *(PROJECT_DIR / "tests").glob("*.py")]
    runnable = [path.name for path in files
                if re.search(r"^if __name__ == .__main__.:", path.read_text(encoding="utf-8"), re.MULTILINE)]
    assert runnable == ["main.py"]            # every other file only defines things: main.py wires and runs them
