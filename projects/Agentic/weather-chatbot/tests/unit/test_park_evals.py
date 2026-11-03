"""
tests/unit/test_park_evals.py: park retrieval evaluations grade destination identity, source evidence and abstention;
the live answer evaluator keeps citation targets, rather than treating a plausible source label as evidence.
"""

import asyncio
from datetime import date
from typing import Any

from nimbus.goldens import Expect, Golden
from nimbus.parks import ParkKnowledge
from tools.eval_parks import INDEX_PATH, ParkCase, grade_retrieval, read_cases, run_cases, to_report
from tools.evals import grade, read_answer


def example(**changes: Any) -> ParkCase:
    """A labeled Narrows clothing question, with any requested expectation replaced."""
    values: dict[str, Any] = {
        "id": "narrows-clothing",
        "destination": "The Narrows",
        "destination_id": "zion-narrows",
        "query": "What clothing should I carry?",
        "document_ids": ["zion-narrows-safety"],
        "evidence_terms": ["warm clothing"],
    }
    return ParkCase.model_validate(values | changes)


def passage(**changes: Any) -> dict[str, Any]:
    """A small returned passage with enough provenance to grade the retrieval."""
    return {
        "id": "clothing-1",
        "document_id": "zion-narrows-safety",
        "destination_ids": ["zion-narrows"],
        "text": "Carry warm clothing in a waterproof bag.",
        "source_url": "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm",
        **changes,
    }


def test_retrieval_needs_the_labeled_source_and_evidence_in_the_same_passage() -> None:
    case = example()
    assert grade_retrieval(case, {"status": "found", "passages": [passage()]}) == []
    wrong = passage(document_id="another-guide")
    absent = passage(text="Ask a ranger about conditions.")
    misses = grade_retrieval(case, {"status": "found", "passages": [wrong, absent]})
    assert "supporting passage missing" in misses


def test_a_relevant_passage_from_another_destination_fails() -> None:
    wrong = passage(destination_ids=["yosemite"])
    assert "passage belongs to another destination" in grade_retrieval(
        example(), {"status": "found", "passages": [wrong]}
    )


def test_a_no_evidence_case_must_return_no_passages() -> None:
    case = example(expected_status="not_found", document_ids=[], evidence_terms=[])
    assert grade_retrieval(case, {"status": "not_found", "passages": []}) == []
    assert "unexpected passages" in grade_retrieval(case, {"status": "not_found", "passages": [passage()]})


def test_each_case_resolves_before_search_and_unsupported_cases_skip_search() -> None:
    searched: list[tuple[str, str, date | None]] = []

    class Knowledge:
        """A deterministic destination registry and search, without external services."""

        def resolve(self, query: str) -> dict[str, Any]:
            """Resolve only the supported destination."""
            if query == "Atlantis":
                return {"status": "unsupported", "candidates": []}
            return {"status": "resolved", "candidates": [{"id": "zion-narrows"}]}

        async def search(self, destination_id: str, query: str, visit_date: date | None = None) -> dict[str, Any]:
            """Record the invocation and return the labeled passage."""
            searched.append((destination_id, query, visit_date))
            return {"status": "found", "passages": [passage()], "retrieval_mode": "lexical"}

    cases = [
        example(visit_date="2027-01-10"),
        example(id="unsupported", destination="Atlantis", destination_id=None, resolution="unsupported"),
    ]
    results = asyncio.run(run_cases(Knowledge(), cases))
    assert all(result.passed for result in results)
    assert searched == [("zion-narrows", "What clothing should I carry?", date(2027, 1, 10))]
    assert "2 of 2 passed" in to_report(results)[-1]
    assert not any("What clothing" in line for line in to_report(results))


def test_live_evaluation_keeps_answer_citations_without_counting_source_cards() -> None:
    fragment = (
        '<a href="https://www.nps.gov/unused.htm">A source card</a>'
        '<div class="answer"><p>Bring layers. '
        '<a href="https://www.nps.gov/zion/guide.htm?a=1&amp;b=2">NPS</a></p></div>'
    )
    answer = read_answer([fragment])
    assert answer.citations == ["https://www.nps.gov/zion/guide.htm?a=1&b=2"]
    assert answer.text == "Bring layers. NPS"


def test_live_evaluation_checks_required_and_permitted_citation_targets() -> None:
    golden = Golden(
        id="cited", question="Prepare for Zion", expect=Expect(cites=["https://www.nps.gov/zion/guide.htm"])
    )
    missing = read_answer(['<div class="answer">According to NPS, bring layers.</div>'])
    assert grade(golden, missing) == ["missing citation https://www.nps.gov/zion/guide.htm"]
    restricted = golden.model_copy(update={"expect": Expect(only_cites=["https://www.nps.gov/zion/guide.htm"])})
    wrong = read_answer(['<div class="answer"><a href="https://example.com">NPS</a></div>'])
    assert grade(restricted, wrong) == ["unexpected citation https://example.com"]


def test_reviewed_cases_cover_each_park_and_have_evidence_labels() -> None:
    cases = read_cases()
    assert len(cases) >= 30
    assert {case.destination_id for case in cases if case.destination_id} == {
        "zion",
        "zion-narrows",
        "grand-canyon",
        "grand-canyon-south-kaibab",
        "yosemite",
        "yosemite-mist-trail",
    }
    assert all(
        case.document_ids and case.evidence_terms
        for case in cases
        if case.resolution == "resolved" and case.expected_status == "found"
    )


def test_bundled_corpus_returns_labeled_evidence_without_crossing_destinations() -> None:
    results = asyncio.run(run_cases(ParkKnowledge(INDEX_PATH), read_cases()))
    assert all(result.passed for result in results), "\n".join(to_report(results))


def test_rank_sensitive_cases_fail_even_when_evidence_is_somewhere_in_the_top_four() -> None:
    case = example(max_evidence_rank=1)
    result = {"status": "found", "passages": [passage(text="Unrelated heading."), passage()]}
    assert grade_retrieval(case, result) == ["supporting passage below rank 1"]


def test_corpus_benchmark_contains_paraphrases_name_conflicts_and_dated_safety_cases() -> None:
    cases = read_cases()
    assert len([case for case in cases if "paraphrase" in case.id]) >= 6
    assert {"mist-spray-spring", "mist-spray-summer", "yellowstone-canyon-collision", "kanarra-collision"} <= {
        case.id for case in cases
    }
