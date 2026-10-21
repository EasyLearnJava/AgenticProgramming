"""
Set up and run this project in one step: create .venv the first time, install the packages into it, then run
knowledge_base_loader.py with any options given.

Usage:
    python run.py                        # from this folder
    python run.py --log-level DEBUG      # options go to knowledge_base_loader.py
    python "projects/RAG/IT Knowledge Base/01-read-the-knowledge-base/run.py"    # from the repo root
"""
import logging
import subprocess
import sys
import venv
from pathlib import Path

logger = logging.getLogger(__name__)

FOLDER = Path(__file__).resolve().parent
VENV = FOLDER / ".venv"
# The venv's own Python: using it directly means there's nothing to activate
PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    """Create .venv if needed, install the packages, run the loader. Returns the loader's exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Step 1: Create the venv, the first time only
    if not PYTHON.exists():
        logger.info("Creating %s (first run only)", VENV)
        venv.create(VENV, with_pip=True)

    # Step 2: Install the packages; quick when they're already there
    logger.info("Installing packages from requirements-dev.txt")
    subprocess.run([PYTHON, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "-r", FOLDER / "requirements-dev.txt"], check=True)

    # Step 3: Run the loader with the venv's Python
    return subprocess.run([PYTHON, FOLDER / "knowledge_base_loader.py", *sys.argv[1:]]).returncode


if __name__ == "__main__":
    sys.exit(main())
