"""LangGraph owns routing and approvals. Checkpoints store the run between steps."""

import operator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .agents import LiveResearch, merge_findings, unique_sources
from .demo import DemoResearch
from .models import FIELDS, LABELS, BriefingSummary, Company, FieldName, Profile, review_candidates
from .providers import ProviderError


class ResearchState(TypedDict, total=False):
    company: dict
    mode: str
    as_of: str
    candidates: list[dict]
    discovery_sources: list[dict]
    discovery_notes: list[str]
    rediscoveries: int
    profiles: list[dict]
    blocked: list[int]
    followups: dict[str, FieldName]
    manual_pass: bool
    briefing: dict
    outcome: str
    events: Annotated[list[str], operator.add]


def build_graph(live: LiveResearch, checkpointer):
    demo = DemoResearch()

    def backend(state: ResearchState) -> LiveResearch | DemoResearch:
        return demo if state["mode"] == "demo" else live

    def discover(state: ResearchState) -> dict:
        candidates, sources, notes = backend(state).discover(
            Company.model_validate(state["company"]), date.fromisoformat(state["as_of"]),
        )
        return {
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "discovery_sources": [source.model_dump(mode="json") for source in sources],
            "discovery_notes": list(dict.fromkeys(notes)),
            "outcome": "",
            "events": [f"Discovery proposed {len(candidates)} of 3 competitors."],
        }

    def shortlist_review(state: ResearchState) -> dict:
        decision = interrupt({"kind": "shortlist"})
        action = decision.get("action") if isinstance(decision, dict) else None
        if action == "retry" and not state.get("rediscoveries"):
            return {"outcome": "rediscover", "rediscoveries": 1, "events": ["Requested a new discovery attempt."]}
        if action != "confirm":
            return {"outcome": "discarded", "events": ["Research stopped at shortlist review."]}

        company = Company.model_validate(state["company"])
        rows = decision.get("candidates", [])
        candidates = review_candidates(rows, company)
        proposed = {(row["name"].casefold(), row["website"]): row for row in state["candidates"]}
        confirmed = []
        for item in candidates:
            suggestion = proposed.get((item.name.casefold(), item.website))
            # Preserve discovery links only if the name, site and reason still match the proposal.
            ids = suggestion["discovery_ids"] if suggestion and item.reason == suggestion["reason"] else []
            confirmed.append(item.model_copy(update={"discovery_ids": ids}))
        return {
            "profiles": [Profile(competitor=item).model_dump(mode="json") for item in confirmed],
            "outcome": "research",
            "events": ["Competitor list approved. Research started for three competitors."],
        }

    def research(state: ResearchState) -> dict:
        company = Company.model_validate(state["company"])
        as_of = date.fromisoformat(state["as_of"])
        plan = state.get("followups", {})
        profiles = [Profile.model_validate(row) for row in state["profiles"]]
        service = backend(state)

        def gather_one(item: tuple[int, Profile]) -> tuple[Profile, bool]:
            index, profile = item
            if plan and str(index) not in plan:
                return profile, index in state.get("blocked", [])
            fields = (plan[str(index)],) if plan else FIELDS
            sources, notes, blocked = service.gather(
                company, profile.competitor, as_of, fields, follow_up=bool(plan),
            )
            return profile.model_copy(update={
                "sources": unique_sources([*profile.sources, *sources]),
                "notes": list(dict.fromkeys([*profile.notes, *notes])),
            }), blocked

        # Distinct competitors can research in parallel. The output stays in shortlist order.
        with ThreadPoolExecutor(max_workers=3) as workers:
            results = list(workers.map(gather_one, enumerate(profiles)))
        return {
            "profiles": [profile.model_dump(mode="json") for profile, _ in results],
            "blocked": [index for index, (_, blocked) in enumerate(results) if blocked],
            "events": [
                f"{'Follow-up' if plan else 'Research'} collected "
                f"{sum(len(profile.sources) for profile, _ in results)} cumulative evidence excerpts.",
            ],
        }

    def extract(state: ResearchState) -> dict:
        service = backend(state)
        as_of = date.fromisoformat(state["as_of"])
        plan = state.get("followups", {})
        profiles = [Profile.model_validate(row) for row in state["profiles"]]

        def analyze_one(item: tuple[int, Profile]) -> tuple[Profile, bool]:
            index, profile = item
            blocked = index in state.get("blocked", [])
            if plan and str(index) not in plan:
                return profile, blocked
            try:
                proposed = service.analyze(profile, as_of)
            except ProviderError as error:
                return profile.model_copy(update={
                    "notes": list(dict.fromkeys([*profile.notes, str(error)])),
                }), blocked or error.permanent
            if plan:
                proposed = [finding for finding in proposed if finding.field == plan[str(index)]]
            return profile.model_copy(update={
                "findings": merge_findings(profile.findings, proposed),
            }), blocked

        with ThreadPoolExecutor(max_workers=3) as workers:
            results = list(workers.map(analyze_one, enumerate(profiles)))
        return {
            "profiles": [profile.model_dump(mode="json") for profile, _ in results],
            "blocked": [index for index, (_, blocked) in enumerate(results) if blocked],
            "events": [f"Analysis found evidence for {sum(4 - len(profile.gaps) for profile, _ in results)} of 12 fields."],
        }

    def followup_plan(state: ResearchState, *, include_blocked: bool = False) -> tuple[dict, str]:
        plan = {}
        labels = []
        for index, row in enumerate(state["profiles"]):
            profile = Profile.model_validate(row)
            if profile.gaps and (include_blocked or index not in state.get("blocked", [])):
                field = profile.gaps[0]
                plan[str(index)] = field
                labels.append(f"{profile.competitor.name} ({LABELS[field].lower()})")
        return plan, ", ".join(labels)

    def route_gaps(state: ResearchState) -> dict:
        # One automatic pass, one highest-priority missing field per competitor.
        if state.get("followups"):
            gaps = sum(len(Profile.model_validate(row).gaps) for row in state["profiles"])
            message = f"Follow-up complete. {gaps} fields remain unsupported." if gaps else "Follow-up resolved all evidence gaps."
            return {"outcome": "briefing", "events": [message]}
        plan, labels = followup_plan(state)
        if plan:
            return {"outcome": "research", "followups": plan, "events": [f"Targeted follow-up: {labels}."]}
        return {"outcome": "briefing", "events": ["Evidence review finished."]}

    def briefing_review(state: ResearchState) -> dict:
        decision = interrupt({"kind": "briefing"})
        action = decision.get("action") if isinstance(decision, dict) else None
        if action == "approve":
            return {"outcome": "approved", "events": ["Briefing approved. Markdown and CSV are available."]}
        if action == "retry" and not state.get("manual_pass"):
            plan, labels = followup_plan(state, include_blocked=True)
            if plan:
                return {
                    "outcome": "research", "followups": plan, "manual_pass": True,
                    "events": [f"Reviewer requested a final pass: {labels}."],
                }
        return {"outcome": "discarded", "events": ["Briefing discarded."]}

    def compile_briefing(state: ResearchState) -> dict:
        profiles = [Profile.model_validate(row) for row in state["profiles"]]
        summary = BriefingSummary.from_profiles(profiles)
        return {
            "briefing": summary.model_dump(),
            "events": [f"Compiled a briefing with {summary.cited_pages} cited pages."],
        }

    graph = StateGraph(ResearchState)
    graph.add_node("discover", discover)
    graph.add_node("shortlist_review", shortlist_review)
    graph.add_node("research", research)
    graph.add_node("extract", extract)
    graph.add_node("route_gaps", route_gaps)
    graph.add_node("compile_briefing", compile_briefing)
    graph.add_node("briefing_review", briefing_review)
    graph.add_edge(START, "discover")
    graph.add_edge("discover", "shortlist_review")
    graph.add_conditional_edges("shortlist_review", lambda s: s["outcome"], {
        "rediscover": "discover", "research": "research", "discarded": END,
    })
    graph.add_edge("research", "extract")
    graph.add_edge("extract", "route_gaps")
    graph.add_conditional_edges("route_gaps", lambda s: s["outcome"], {
        "research": "research", "briefing": "compile_briefing",
    })
    graph.add_edge("compile_briefing", "briefing_review")
    graph.add_conditional_edges("briefing_review", lambda s: s["outcome"], {
        "research": "research", "approved": END, "discarded": END,
    })
    return graph.compile(checkpointer=checkpointer)
