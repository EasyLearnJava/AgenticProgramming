"""
Run one IT Knowledge Base project in one step: create its .venv the first time, install its packages into it, make
its .env from its .env.example if it has none, then run it from its own folder with the venv's Python, so there's
nothing to activate. Works the same on Windows, macOS, Linux and GitHub Codespaces.

A new .env holds only the example's placeholder. If the setting it names (GOOGLE_API_KEY) isn't in the environment
either, such as from a Codespaces secret, the run stops there and says where to put the key; a key is never printed.

Usage (from the repo root):
    python "projects/RAG/IT Knowledge Base/run.py" Basic/01-read-the-knowledge-base
    # options after the project's name go to it:
    python "projects/RAG/IT Knowledge Base/run.py" Advanced/01-read-the-knowledge-base --log-level DEBUG
"""
import argparse
import logging
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

logger = logging.getLogger(__name__)

SERIES = Path(__file__).resolve().parent

# Each project's run command, as its README gives it, without `python`: the project's venv Python runs it
COMMANDS = {
    "Basic/01-read-the-knowledge-base": ["pipeline.py"],
    "Basic/02-documents-and-metadata": ["pipeline.py"],
    "Basic/03-chunking": ["pipeline.py"],
    "Basic/04-embeddings": ["pipeline.py"],
    "Basic/05-vector-store": ["pipeline.py"],
    "Basic/06-retriever": ["pipeline.py"],
    "Basic/07-grounded-answer": ["pipeline.py"],
    "Basic/08-rag-engine": ["pipeline.py"],
    "Basic/09-api": ["-m", "uvicorn", "main:app"],
    "Basic/10-chat-page": ["-m", "uvicorn", "main:app"],
    "Intermediate/01-rag-chat-app": ["main.py"],
    "Advanced/01-read-the-knowledge-base": ["knowledge_base_loader.py"],
    "Advanced/02-documents-and-metadata": ["knowledge_base_loader.py"],
    "Advanced/03-chunking": ["pipeline.py"],
    "Advanced/04-embeddings": ["pipeline.py"],
    "Advanced/05-vector-store": ["pipeline.py"],
    "Advanced/06-retriever": ["pipeline.py"],
    "Advanced/07-grounded-answer": ["pipeline.py"],
}


def venv_python(project: Path) -> Path:
    """The Python inside a project's .venv."""
    return project / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def make_env_file(folder: Path) -> bool:
    """Copy the project's .env.example to .env when it has none. Returns False when the settings the example names
    aren't in the environment either: the new .env holds only placeholders, so the user must fill it in first."""
    example, env_file = folder / ".env.example", folder / ".env"
    if not example.is_file() or env_file.exists():
        return True
    shutil.copyfile(example, env_file)
    logger.info("Created %s from .env.example (.env is in .gitignore: it never goes into git)", env_file)
    names = [line.split("=", 1)[0].strip() for line in example.read_text(encoding="utf-8").splitlines()
             if "=" in line and not line.lstrip().startswith("#")]
    missing = [name for name in names if not os.environ.get(name, "").strip()]
    if missing:
        logger.error("Open %s, put your key after %s=, save it, then run this command again. (In GitHub Codespaces, "
                     "a Codespaces secret named %s works too: then .env isn't needed.)", env_file,
                     "= and ".join(missing), " and ".join(missing))
        return False
    logger.info("%s is set in the environment, which wins over .env", ", ".join(names))
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The project's folder name, then any options for the project."""
    parser = argparse.ArgumentParser(description="Set up and run one IT Knowledge Base project in one step.")
    # Windows tab completion writes Basic\01-...\ : the same project as Basic/01-...
    parser.add_argument("project", type=lambda name: name.replace("\\", "/").rstrip("/"), choices=COMMANDS,
                        metavar="PROJECT", help="the project's folder: " + ", ".join(COMMANDS))
    parser.add_argument("options", nargs=argparse.REMAINDER, help="options passed on to the project")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Set up and run the project. Returns its exit code."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    folder = SERIES / args.project
    python = venv_python(folder)

    # Step 1: Create the project's venv, the first time only
    if not python.exists():
        logger.info("Creating %s (first run only)", folder / ".venv")
        venv.create(folder / ".venv", with_pip=True)

    # Step 2: Install its packages; quick when they're already there
    logger.info("Installing %s's packages from requirements-dev.txt", args.project)
    install = subprocess.run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                              "-r", "requirements-dev.txt"], cwd=folder)
    if install.returncode != 0:
        logger.error("Installing the packages failed: pip's message is above")
        return install.returncode

    # Step 3: Make its .env from its .env.example, the first time only; stop if the key must be put in first
    if not make_env_file(folder):
        return 1

    # Step 4: Run it from its own folder, as its README does
    command = COMMANDS[args.project] + args.options
    logger.info("Running %s in %s", " ".join(command), args.project)
    try:
        return subprocess.run([python, *command], cwd=folder).returncode
    except KeyboardInterrupt:                  # Ctrl+C, e.g. to stop a server: no traceback
        return 130


if __name__ == "__main__":
    sys.exit(main())
