"""Promote human-authored, synthetic park intake regressions for the replay harness."""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from tools.harness_replay import IntakeCase, run_intake_case

REGRESSIONS = Path(__file__).resolve().parents[1] / "evals" / "harness" / "regressions"
MAX_CASE_BYTES = 16384


class ReviewedCase(BaseModel):
    """A reviewer records the class of error and writes a fresh example with the expected behavior."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    category: Literal["trip-dates", "destination", "travel"]
    case: IntakeCase


def read_review(path: Path) -> ReviewedCase:
    with path.open("rb") as source:
        data = source.read(MAX_CASE_BYTES + 1)
    if len(data) > MAX_CASE_BYTES:
        raise ValueError("Reviewed case exceeds the size limit.")
    review = ReviewedCase.model_validate_json(data)
    # These file stems are reserved on Windows, even with a JSON extension.
    reserved = {"con", "prn", "aux", "nul", *(f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10))}
    if review.case.case_id in reserved:
        raise ValueError("Choose a portable case ID.")
    return review


def reviewed_cases(directory: Path = REGRESSIONS) -> list[IntakeCase]:
    """Fail visibly on renamed, invalid or missing fixtures so the gate cannot silently lose coverage."""
    if not directory.is_dir():
        raise ValueError("Reviewed regressions directory missing.")
    cases = []
    for path in sorted(directory.glob("*.json")):
        case = read_review(path).case
        if case.case_id != path.stem:
            raise ValueError("Reviewed case ID must match its filename.")
        cases.append(case)
    if not cases:
        raise ValueError("No reviewed regressions found.")
    return cases


def promote(review: ReviewedCase, directory: Path = REGRESSIONS) -> Path:
    """Publish a complete file once, even when two reviewers promote the same case concurrently."""
    destination = directory / f"{review.case.case_id}.json"
    directory.mkdir(exist_ok=True, parents=True)
    with NamedTemporaryFile(dir=directory, suffix=".tmp", delete_on_close=False) as draft:
        # Excluding unset fields is essential: an omitted oracle field means 'do not score this field'.
        draft.write((review.model_dump_json(exclude_unset=True, indent=2) + "\n").encode())
        draft.close()
        destination.hardlink_to(draft.name)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    preview = actions.add_parser("preview", help="Grade a proposed case against the real parser before promotion")
    preview.add_argument("file", type=Path)
    publish = actions.add_parser("promote", help="Add an approved case to the versioned regression suite")
    publish.add_argument("file", type=Path)
    publish.add_argument(
        "--synthetic",
        required=True,
        action="store_true",
        help="Confirm that the example was written for review and contains no visitor conversation or identifiers",
    )
    options = parser.parse_args(argv)
    try:
        review = read_review(options.file)
        if options.command == "preview":
            result = run_intake_case(review.case)
            print(json.dumps(result))
            return int(result["outcome"] != "pass")
        saved = promote(review)
        print(f"Promoted {saved.stem}. Run the replay harness and review the new fixture in your next change.")
    except FileExistsError:
        print("That case ID is already present. Choose another ID or review the existing fixture.")
        return 1
    except (OSError, ValueError, ValidationError):
        # Pydantic's default error output includes the submitted example. Review text stays off CI's console.
        print("Invalid review or inaccessible file. Check the category, case ID, clock, time zone and expected fields.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
