"""
Run one IT Knowledge Base project in one step: create its .venv the first time, install its packages into it, then
run it from its own folder with the venv's Python, so there's nothing to activate.

Usage (from the repo root):
    python "projects/RAG/IT Knowledge Base/run.py" Basic/01-read-the-knowledge-base
    python "projects/RAG/IT Knowledge Base/run.py" Advanced/01-read-the-knowledge-base --log-level DEBUG   # options go to it
"""
import argparse
import logging
import subprocess
import sys
import venv
from pathlib import Path

logger = logging.getLogger(__name__)

SERIES = Path(__file__).resolve().parent

# Each project's run command, as its README gives it, without `python`: the project's venv Python runs it
COMMANDS = {
    "Basic/01-read-the-knowledge-base": ["knowledge_base_loader.py"],
    "Basic/02-documents-and-metadata": ["knowledge_base.py"],
    "Basic/03-chunking": ["chunking.py"],
    "Basic/04-embeddings": ["embed_chunks.py"],
    "Basic/05-vector-store": ["vector_store.py"],
    "Basic/06-retriever": ["retriever.py"],
    "Basic/07-grounded-answer": ["rag_chain.py"],
    "Basic/08-rag-engine": ["rag_engine.py"],
    "Basic/09-api": ["-m", "uvicorn", "main:app", "--reload"],
    "Basic/10-chat-page": ["-m", "uvicorn", "main:app", "--reload"],
    "Basic/11-qdrant-in-docker": ["-m", "uvicorn", "main:app", "--reload"],
    "Basic/12-tuning": ["tuning.py"],
    "Advanced/01-read-the-knowledge-base": ["knowledge_base_loader.py"],
}


def venv_python(project: Path) -> Path:
    """The Python inside a project's .venv."""
    return project / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


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

    # Step 3: Run it from its own folder, as its README does
    command = COMMANDS[args.project] + args.options
    logger.info("Running %s in %s", " ".join(command), args.project)
    try:
        return subprocess.run([python, *command], cwd=folder).returncode
    except KeyboardInterrupt:                  # Ctrl+C, e.g. to stop a server: no traceback
        return 130


if __name__ == "__main__":
    sys.exit(main())
