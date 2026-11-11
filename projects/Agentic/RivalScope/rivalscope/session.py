"""The UI uses this boundary to start, resume, or inspect a saved run."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import RLock

import httpx
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .agents import LiveResearch
from .config import Settings
from .demo import DEMO_COMPANY, DEMO_DATE
from .models import BriefingSummary, Company, Profile, review_candidates
from .providers import Nebius, Tavily
from .workflow import build_graph

# Serialize writes in the local app. Each action rechecks its checkpoint before resuming it.
_write_lock = RLock()


@dataclass
class Run:
    state: dict
    phase: str
    checkpoint: str | None = None

    @property
    def profiles(self) -> list[Profile]:
        return [Profile.model_validate(row) for row in self.state.get("profiles", [])]

    @property
    def summary(self) -> BriefingSummary:
        return BriefingSummary.model_validate(self.state["briefing"])


def _run(snapshot) -> Run:
    state = dict(snapshot.values)
    if "company" not in state:
        return Run({}, "new")
    for task in snapshot.tasks:
        for pause in task.interrupts:
            return Run(state, pause.value["kind"], snapshot.config["configurable"]["checkpoint_id"])
    if snapshot.next:
        return Run(state, "interrupted", snapshot.config["configurable"]["checkpoint_id"])
    return Run(state, state["outcome"])


class ResearchSession:
    def __init__(self, database: Path, settings: Settings, run_id: str):
        self.database = database
        self.settings = settings
        self.config = {"configurable": {"thread_id": run_id}, "recursion_limit": 35}

    @contextmanager
    def _graph(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(self.database)) as saver, httpx.Client(
            timeout=httpx.Timeout(35, connect=8),
        ) as client:
            live = LiveResearch(Tavily(self.settings.tavily_key, client), Nebius(self.settings, client))
            yield build_graph(live, saver)

    def status(self) -> Run:
        with self._graph() as graph:
            return _run(graph.get_state(self.config))

    def start(self, company: Company, mode: str) -> None:
        if mode not in {"demo", "live"}:
            raise ValueError("Choose Demo or Live mode.")
        if mode == "live" and self.settings.missing_keys:
            raise ValueError("Set both API keys before starting Live research.")
        if mode == "demo":
            company = DEMO_COMPANY
        as_of = DEMO_DATE if mode == "demo" else date.today()
        with _write_lock, self._graph() as graph:
            if _run(graph.get_state(self.config)).phase != "new":
                raise ValueError("This run already exists. Start a new run for a different company.")
            graph.invoke({
                "company": company.model_dump(), "mode": mode, "as_of": as_of.isoformat(),
                "events": [f"Started {mode} research for {company.name}."],
            }, self.config)

    def advance(self, phase: str, checkpoint: str, action: str, rows: list[dict] | None = None) -> None:
        with _write_lock, self._graph() as graph:
            run = _run(graph.get_state(self.config))
            if (phase, checkpoint) != (run.phase, run.checkpoint):
                raise ValueError("This review has changed. Refresh the page and review the latest version.")
            if phase == "interrupted" and action == "retry":
                graph.invoke(None, self.config)
                return
            valid_actions = {
                "shortlist": {"confirm", "retry", "discard"},
                "briefing": {"approve", "retry", "discard"},
            }
            if action not in valid_actions.get(phase, set()):
                raise ValueError("That action is unavailable at this step.")
            decision = {"action": action}
            if action == "confirm":
                company = Company.model_validate(run.state["company"])
                decision["candidates"] = [item.model_dump() for item in review_candidates(rows or [], company)]
            if action == "retry":
                if phase == "shortlist" and run.state.get("rediscoveries"):
                    raise ValueError("Discovery retry was already used.")
                if phase == "briefing" and (run.state.get("manual_pass") or not any(p.gaps for p in run.profiles)):
                    raise ValueError("A further evidence pass is unavailable.")
            graph.invoke(Command(resume=decision), self.config)
