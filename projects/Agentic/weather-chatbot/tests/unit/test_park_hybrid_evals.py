"""Hybrid comparison grades actual evidence and failures, with bounded dense selections and text-free reports."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from nimbus.config import Settings
from nimbus.parks import MAX_CONTEXT_CHARS, MAX_PASSAGES
from tests.unit.test_park_evals import example, passage
from tools import eval_park_hybrid
from tools.eval_parks import grade_retrieval

PRIVATE = "private question or returned passage marker"


def candidate(identity: str, rank: int | None, text: str = "Carry warm clothing.") -> dict[str, Any]:
    """One diagnostic row; only a qualified dense rank may enter the semantic-only comparison."""
    return {"semantic_rank": rank, "chunk": passage(id=identity, text=text)}


def result(*passages: dict[str, Any], status: str = "ready", **changes: Any) -> dict[str, Any]:
    """A deterministic retrieval result whose public evidence and dense diagnostics can differ."""
    return {
        "status": "found" if passages else "not_found",
        "passages": list(passages),
        "semantic_status": status,
        "diagnostics": {"candidates": []},
        **changes,
    }


def test_semantic_only_uses_dense_rank_and_never_pads_with_nonqualifying_chunks() -> None:
    rows = [candidate("unqualified", None)]
    rows.extend(candidate(f"dense-{rank}", rank) for rank in range(MAX_PASSAGES + 2, 0, -1))
    original = result(passage(id="hybrid-only"), diagnostics={"candidates": rows})
    dense = eval_park_hybrid.semantic_only(original)
    assert [item["id"] for item in dense["passages"]] == [f"dense-{rank}" for rank in range(1, MAX_PASSAGES + 1)]
    assert dense["status"] == "found"
    assert original["passages"][0]["id"] == "hybrid-only"


def test_semantic_only_skips_oversize_passages_and_respects_the_exact_context_budget() -> None:
    rows = [
        candidate("too-large", 1, "a" * (MAX_CONTEXT_CHARS + 1)),
        candidate("exact-limit", 2, "b" * MAX_CONTEXT_CHARS),
        candidate("no-room", 3, "c"),
    ]
    dense = eval_park_hybrid.semantic_only(result(diagnostics={"candidates": rows}))
    assert [item["id"] for item in dense["passages"]] == ["exact-limit"]
    assert sum(len(item["text"]) for item in dense["passages"]) == MAX_CONTEXT_CHARS


def test_semantic_only_reports_no_evidence_when_the_dense_branch_returned_no_qualifying_scores() -> None:
    dense = eval_park_hybrid.semantic_only(
        result(passage(), diagnostics={"candidates": [candidate("keyword-only", None)]})
    )
    assert dense["status"] == "not_found"
    assert dense["passages"] == []


def test_semantic_provider_failure_cannot_pass_an_expected_abstention() -> None:
    """Unavailable dense scoring is not a successful no-match search, even on an unanswerable case."""
    dense = eval_park_hybrid.semantic_only(result(status="timeout"))
    assert dense["status"] == "unavailable"
    assert grade_retrieval(example(expected_status="not_found"), dense) == ["expected not_found, got unavailable"]


@pytest.mark.parametrize("position", [0, 1])
def test_forbidden_sections_fail_even_when_the_required_source_evidence_was_retrieved(position: int) -> None:
    passages = [passage(section="Clothing")]
    passages.insert(position, passage(id="winter", section="Winter", text="A different seasonal warning."))
    assert grade_retrieval(example(forbidden_sections=["Winter"]), result(*passages)) == [
        "passage belongs to an excluded season or section"
    ]
    assert grade_retrieval(example(forbidden_sections=["Winter"]), result(passage(section="Clothing"))) == []


class RecordedSearch:
    """A hosted or lexical profile used only to exercise grading; it cannot make network calls."""

    semantic_provider = "qdrant"
    index_version = "reviewed-public-fixture"

    def __init__(self, results: dict[str, dict[str, Any]]) -> None:
        self.results = results
        self.calls: list[tuple[str, str, date | None, bool]] = []

    async def search(
        self, destination: str, query: str, visit_date: date | None = None, *, explain: bool = False
    ) -> dict[str, Any]:
        """Return the recording and retain scope so tests detect skipped or extra evaluation cases."""
        self.calls.append((destination, query, visit_date, explain))
        return self.results[query]


def bind_profiles(monkeypatch: pytest.MonkeyPatch, lexical: RecordedSearch, hosted: RecordedSearch) -> Settings:
    """Replace both profile constructors without loading local settings, credentials, or native embeddings."""
    monkeypatch.setattr(
        eval_park_hybrid,
        "make_park_knowledge",
        lambda settings: lexical if settings.parks_retrieval_mode == "lexical" else hosted,
    )
    return Settings(_env_file=None)


def test_comparison_reports_profile_ranks_without_counting_abstentions_as_retrieval_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    questions = [f"{PRIVATE} {number}" for number in range(3)]
    evidence = passage(text=f"Carry warm clothing. {PRIVATE}")
    other = passage(text=f"No matching evidence. {PRIVATE}")
    cases = [
        example(id="first", query=questions[0], visit_date=date(2027, 4, 1)),
        example(id="second", query=questions[1]),
        example(id="abstain", query=questions[2], expected_status="not_found", document_ids=[], evidence_terms=[]),
        example(id="unresolved", resolution="unsupported", query="This must not be searched."),
    ]
    lexical = RecordedSearch({questions[0]: result(evidence), questions[1]: result(other), questions[2]: result()})
    hosted = RecordedSearch(
        {
            questions[0]: result(
                other, evidence, diagnostics={"candidates": [candidate("support", 1, evidence["text"])]}
            ),
            questions[1]: result(
                evidence,
                diagnostics={"candidates": [candidate("other", 1, other["text"]), candidate("support", 2)]},
            ),
            questions[2]: result(),
        }
    )
    report = asyncio.run(eval_park_hybrid.compare(bind_profiles(monkeypatch, lexical, hosted), cases))
    assert report["provider_failures"] == 0
    assert report["summary"]["lexical"] == {"passed": 2, "cases": 3, "recall_at_4": 0.5, "top_1": 0.5, "mrr_at_4": 0.5}
    for profile in ("semantic", "hybrid"):
        assert report["summary"][profile] == {
            "passed": 3,
            "cases": 3,
            "recall_at_4": 1.0,
            "top_1": 0.5,
            "mrr_at_4": 0.75,
        }
    assert [row["id"] for row in report["cases"]] == ["first", "second", "abstain"]
    assert len(hosted.calls) == len(lexical.calls) == 3
    assert hosted.calls[0] == ("zion-narrows", questions[0], date(2027, 4, 1), True)
    assert all(not call[3] for call in lexical.calls)
    assert PRIVATE not in json.dumps(report)
    assert "https://www.nps.gov" not in json.dumps(report)


def test_provider_outage_remains_a_failure_even_when_keyword_fallback_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    case = example(query=PRIVATE)
    lexical = RecordedSearch({PRIVATE: result(passage())})
    hosted = RecordedSearch({PRIVATE: result(passage(), status="timeout")})
    report = asyncio.run(eval_park_hybrid.compare(bind_profiles(monkeypatch, lexical, hosted), [case]))
    assert report["provider_failures"] == 1
    assert report["summary"]["lexical"]["passed"] == report["summary"]["hybrid"]["passed"] == 1
    assert report["summary"]["semantic"]["passed"] == 0
    assert report["cases"][0]["semantic_status"] == "timeout"
    assert PRIVATE not in json.dumps(report)


def test_command_fails_provider_outages_and_writes_only_the_sanitized_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = example(query=PRIVATE)
    lexical = RecordedSearch({PRIVATE: result(passage(text=f"warm clothing {PRIVATE}"))})
    hosted = RecordedSearch({PRIVATE: result(passage(text=f"warm clothing {PRIVATE}"), status="timeout")})
    settings = bind_profiles(monkeypatch, lexical, hosted)
    monkeypatch.setattr(eval_park_hybrid, "Settings", lambda **_kwargs: settings)
    monkeypatch.setattr(eval_park_hybrid, "read_cases", lambda _path: [case])
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["eval_park_hybrid", "--output", str(output)])
    assert eval_park_hybrid.main() == 1
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["provider_failures"] == 1
    assert saved["summary"]["hybrid"]["passed"] == 1
    assert PRIVATE not in output.read_text(encoding="utf-8") + capsys.readouterr().out


@pytest.mark.parametrize(("rank", "expected_exit"), [(1, 0), (2, 1)])
def test_command_rejects_rank_regressions_even_when_every_case_and_provider_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rank: int, expected_exit: int
) -> None:
    evidence = passage()
    returned = [passage(text="Unrelated guidance.")] * (rank - 1) + [evidence]
    lexical = RecordedSearch({PRIVATE: result(evidence)})
    hosted = RecordedSearch({PRIVATE: result(*returned)})
    settings = bind_profiles(monkeypatch, lexical, hosted)
    monkeypatch.setattr(eval_park_hybrid, "Settings", lambda **_kwargs: settings)
    monkeypatch.setattr(eval_park_hybrid, "read_cases", lambda _path: [example(query=PRIVATE)])
    output = tmp_path / "quality.json"
    monkeypatch.setattr("sys.argv", ["eval_park_hybrid", "--output", str(output)])
    assert eval_park_hybrid.main() == expected_exit
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["provider_failures"] == 0
    assert saved["summary"]["hybrid"]["passed"] == saved["summary"]["lexical"]["passed"] == 1
    assert saved["quality_regressions"] == (["top_1", "mrr_at_4"] if rank == 2 else [])
    assert saved["policy"]["dense_baseline"] == "candidate_cutoff_without_keyword_gate"
    assert saved["policy"]["semantic_candidate_cutoff"] == 0.3
    assert saved["policy"]["semantic_only_admission_cutoff"] == 0.55
    assert saved["policy"]["keyword_weight"] == 1.0
    assert saved["policy"]["semantic_weight"] == 0.1


@pytest.mark.parametrize("only_unresolved", [False, True])
def test_command_rejects_empty_comparisons_without_claiming_a_provider_or_quality_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, only_unresolved: bool
) -> None:
    lexical, hosted = RecordedSearch({}), RecordedSearch({})
    settings = bind_profiles(monkeypatch, lexical, hosted)
    cases = [example(resolution="unsupported")] if only_unresolved else []
    monkeypatch.setattr(eval_park_hybrid, "Settings", lambda **_kwargs: settings)
    monkeypatch.setattr(eval_park_hybrid, "read_cases", lambda _path: cases)
    output = tmp_path / "empty.json"
    monkeypatch.setattr("sys.argv", ["eval_park_hybrid", "--output", str(output)])
    assert eval_park_hybrid.main() == 1
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["cases"] == saved["quality_regressions"] == []
    assert saved["provider_failures"] == 0
    assert saved["summary"]["hybrid"]["cases"] == 0
    assert hosted.calls == lexical.calls == []
