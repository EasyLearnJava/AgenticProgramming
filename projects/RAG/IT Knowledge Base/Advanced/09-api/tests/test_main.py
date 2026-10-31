"""
Tests for main.py: add-key shows a new key once and keeps only its hash; the server won't start with no key; the
feedback command lists the answers rated down and writes them to a CSV file; and the server itself, started as a user
starts it, answers a question over HTTP and writes a JSON access line with its request ID and nothing of the question
or the key.
"""
import csv
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from support import fake_settings

import main
from feedback import FeedbackStore
from security import ApiKeys

FOLDER = Path(__file__).resolve().parent.parent


def test_add_key_shows_the_key_once_and_keeps_only_its_hash(tmp_path, capsys):
    settings = fake_settings(tmp_path)
    assert main.main(["--settings", str(settings), "add-key", "chat-page"]) == 0
    key = capsys.readouterr().out.strip().splitlines()[-1]
    keys_file = tmp_path / "data" / "api_keys.toml"
    assert key.startswith("kb_") and key not in keys_file.read_text(encoding="utf-8")
    assert ApiKeys.load(keys_file).caller(key) == "chat-page"


def test_the_server_wont_start_with_no_key(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(main, "setup_logging", lambda *args, **kwargs: None)    # pytest's handler keeps the lines
    assert main.main(["--settings", str(fake_settings(tmp_path))]) == 1
    assert "No API key yet" in caplog.text and "add-key NAME" in caplog.text


def test_feedback_lists_the_answers_rated_down_and_writes_them_out(tmp_path, capsys):
    settings = fake_settings(tmp_path)
    store = FeedbackStore(tmp_path / "data" / "feedback.sqlite3")
    for request_id, rating, comment in (("r1", "down", "Not for Mac"), ("r2", "up", "")):
        grounded = SimpleNamespace(answer="Open UDP 500.", status="answered", cited=["c1"], prompt_version="answer-v1")
        store.record(request_id, "chat-page", SimpleNamespace(question=f"Q {request_id}", asked=f"Q {request_id}",
                                                              answer=grounded, cached=""), model="fake/m")
        store.rate(request_id, "chat-page", rating, comment)
    written = tmp_path / "rated_down.csv"
    assert main.main(["--settings", str(settings), "feedback", "--csv", str(written)]) == 0
    out = capsys.readouterr().out
    assert "2 answers kept (for 30 days), 1 rated up, 1 rated down" in out
    assert "  r1 (answered, cited 1) Q r1: Not for Mac\n" in out
    with open(written, encoding="utf-8") as file:
        (row,) = list(csv.DictReader(file))
    assert (row["request_id"], row["question"], row["comment"], row["cited"]) == ("r1", "Q r1", "Not for Mac", "c1")


# -------------------------------------------------
# The Server, Started as a User Starts It
# -------------------------------------------------

def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_ready(url: str, seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            with urllib.request.urlopen(f"{url}/health/ready", timeout=2):
                return
        except (urllib.error.URLError, ConnectionError):      # not listening yet, or not ready (503)
            if time.monotonic() > deadline:
                raise
        time.sleep(0.2)


def test_the_server_answers_over_http_and_logs_a_json_line_per_request(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    port = free_port()
    env = {**os.environ, "GOOGLE_API_KEY": "", "KB__API__PORT": str(port)}

    def run(script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, script, "--settings", str(settings), *args], cwd=FOLDER, env=env,
                              capture_output=True, text=True, encoding="utf-8", check=True)

    run("pipeline.py", "--manifest-path", manifest)
    key = run("main.py", "add-key", "e2e").stdout.strip().splitlines()[-1]
    # Its log goes to a file: a pipe that's only read at the end fills up (about 4 KB on Windows), and then the
    # server's next log line blocks it
    log_file = tmp_path / "server.log"
    with open(log_file, "w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "main.py", "--settings", str(settings), "--manifest-path",
                                   manifest], cwd=FOLDER, env=env, stderr=log)
        try:
            url = f"http://127.0.0.1:{port}"
            wait_until_ready(url)
            request = urllib.request.Request(f"{url}/v1/query", data=json.dumps(
                {"question": "Bluebird: my VPN keeps timing out"}).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                body, request_id = json.loads(response.read()), response.headers["X-Request-ID"]
        finally:
            server.terminate()
            server.wait(timeout=30)
    logs = log_file.read_text(encoding="utf-8")
    assert body["status"] == "answered" and body["request_id"] == request_id
    lines = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
    (access,) = [line for line in lines if line["message"] == "POST /v1/query 200"]
    assert (access["request_id"], access["caller"], access["answer_status"]) == (request_id, "e2e", "answered")
    assert "Bluebird" not in logs and key not in logs
