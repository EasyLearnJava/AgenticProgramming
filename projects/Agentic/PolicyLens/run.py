"""Convenient entry point: python run.py; the server stays on this computer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Start the local PolicyLens workspace")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("policylens.api:create_app", factory=True, host="127.0.0.1", port=args.port)

