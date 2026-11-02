"""
tests/unit/test_deploy.py: Vercel's ignore step, from vercel.json, run in sh, as plain POSIX, in the project's folder
of a repository of its own: a push that leaves the folder as it was at the last deploy is skipped (0); a change to it,
in any of the push's commits, a redeploy, the first deploy, or a last deploy older than Vercel's clone builds (1), and
none fails the deploy (any other code; issue 21).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from nimbus.constants import PROJECT_ROOT

SKIP, BUILD = 0, 1
IGNORE_COMMAND = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))["ignoreCommand"]
# git without anyone's own settings or repository: a global hook or signing rule, or a GIT_DIR set by a hook that runs
# the tests, can't reach the test's repositories.
ALONE = {
    **{name: value for name, value in os.environ.items() if not name.startswith("GIT_")},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(repo: Path, *args: str) -> str:
    """Runs git in the repository, and gives back what it printed."""
    path = shutil.which("git")
    assert path, "Vercel's ignore step runs git; the test needs it too"
    command = [path, "-C", str(repo), *args]
    done = subprocess.run(command, env=ALONE, check=True, capture_output=True, text=True)  # noqa: S603
    return done.stdout.strip()


def commit(repo: Path, path: str, text: str) -> str:
    """Writes the file and commits it; its commit's SHA."""
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "-c", "user.name=Nimbus", "-c", "user.email=nimbus@example.com", "commit", "-q", "-m", path)
    return git(repo, "rev-parse", "HEAD")


def ignore_step(repo: Path, previous: str, current: str) -> int:
    """The ignore step's exit code for the project's folder, at the current commit, as Vercel names the two."""
    git(repo, "checkout", "-q", current)
    env = {**ALONE, "VERCEL_GIT_PREVIOUS_SHA": previous, "VERCEL_GIT_COMMIT_SHA": current}
    # sh, as git finds it: on Windows Git's own, never WSL's bash, which the variables don't reach.
    step = [git(repo, "var", "GIT_SHELL_PATH"), "-c", IGNORE_COMMAND]
    return subprocess.run(step, cwd=repo / "weather-chatbot", env=env, check=False).returncode  # noqa: S603


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    return tmp_path


def test_a_push_that_changes_only_another_project_is_skipped(repo: Path) -> None:
    deployed = commit(repo, "weather-chatbot/main.py", "one")
    pushed = commit(repo, "rag/main.py", "two")
    assert ignore_step(repo, deployed, pushed) == SKIP


def test_a_change_to_the_project_a_redeploy_and_the_first_deploy_build(repo: Path) -> None:
    deployed = commit(repo, "weather-chatbot/main.py", "one")
    pushed = commit(repo, "weather-chatbot/main.py", "two")
    assert ignore_step(repo, deployed, pushed) == BUILD
    assert ignore_step(repo, pushed, pushed) == BUILD
    assert ignore_step(repo, "", pushed) == BUILD


def test_a_push_of_several_commits_builds_when_any_of_them_changes_the_project(repo: Path) -> None:
    deployed = commit(repo, "weather-chatbot/main.py", "one")
    commit(repo, "weather-chatbot/main.py", "two")
    pushed = commit(repo, "rag/main.py", "three")
    assert ignore_step(repo, deployed, pushed) == BUILD


def test_a_last_deploy_older_than_vercel_s_clone_builds_and_doesn_t_fail_the_deploy(repo: Path) -> None:
    # Vercel's clone keeps the last 10 commits: git can't find an older one, and its own code, 128, fails the deploy.
    pushed = commit(repo, "weather-chatbot/main.py", "one")
    assert ignore_step(repo, "0" * 40, pushed) == BUILD
