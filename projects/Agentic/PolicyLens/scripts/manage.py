"""CLI operations use the same service as the browser, avoiding duplicated logic."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from policylens.config import load_settings
from policylens.evaluation import run_evaluation
from policylens.service import PolicyService


def main():
    parser = argparse.ArgumentParser(description="Manage PolicyLens")
    parser.add_argument("command", choices=["index", "evaluate", "status", "ask"])
    parser.add_argument("question", nargs="?", default="")
    args = parser.parse_args()
    service = PolicyService(load_settings())
    if args.command == "index":
        result = service.rebuild()
    elif args.command == "evaluate":
        report = run_evaluation(service)
        result = {"report_id": report["id"], "summary": report["summary"]}
    elif args.command == "ask":
        if not args.question:
            parser.error("Supply a quoted question after ask.")
        result = service.ask(args.question).model_dump()
    else:
        result = service.status()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

