"""Streamlit screens. Research logic and approval rules live outside the UI."""

import re
from uuid import UUID, uuid4

import streamlit as st
from pydantic import ValidationError

from .config import CHECKPOINTS, Settings
from .demo import DEMO_COMPANY
from .models import FIELDS, LABELS, Company, Source
from .reports import (
    MISSING, citation, escape, finding_text, findings_in, report_csv, report_markdown,
    source_of, source_type,
)
from .session import ResearchSession, Run


def _id() -> str:
    value = st.query_params.get("run") or st.session_state.get("rivalscope_run")
    try:
        run_id = str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        run_id = str(uuid4())
    st.session_state["rivalscope_run"] = run_id
    if st.query_params.get("run") != run_id:
        st.query_params["run"] = run_id
    return run_id


def _act(message: str, callback) -> None:
    try:
        with st.spinner(message, show_time=True):
            callback()
    except ValidationError as error:
        st.error(" ".join(dict.fromkeys(item["msg"].removeprefix("Value error, ") for item in error.errors())))
    except ValueError as error:
        st.error(str(error))
    except Exception:
        st.error("The workflow stopped unexpectedly. Reload to recover the last saved step.")
    else:
        st.rerun()


def _start(session: ResearchSession, settings: Settings) -> None:
    st.write("Compare three competitors on pricing, product features, positioning, and recent news.")
    mode = st.radio("Research mode", ["demo", "live"], index=0 if settings.default_mode == "demo" else 1,
                    format_func=lambda value: "Trello demo" if value == "demo" else "Live research",
                    horizontal=True)
    missing = mode == "live" and settings.missing_keys
    if missing:
        st.warning("Set " + " and ".join(missing) + " in the local .env file to run live research.")
        st.page_link("pages/documentation.py", label="API key setup", icon=":material/key:")
    with st.form("start_run"):
        if mode == "live":
            name = st.text_input("Company or product", max_chars=100, placeholder="e.g., Trello")
            website = st.text_input("Official website (optional)", max_chars=250, placeholder="trello.com")
            scope = st.text_input("Market focus (optional)", max_chars=240,
                                  placeholder="US work management for small teams")
            st.caption("Live mode sends your research terms to Tavily and relevant excerpts to Nebius.")
        else:
            st.markdown("**Trello**")
            st.caption("US work management for small teams · Public-source snapshot from November 10, 2026")
        if st.form_submit_button("Find competitors", type="primary", disabled=bool(missing)):
            _act("Finding competitors…", lambda: session.start(
                Company(name=name, website=website, scope=scope) if mode == "live" else DEMO_COMPANY, mode,
            ))


def _advance(session: ResearchSession, run: Run, action: str, message: str, rows=None) -> None:
    if run.checkpoint:
        _act(message, lambda: session.advance(run.phase, run.checkpoint, action, rows))


def _review_shortlist(session: ResearchSession, run: Run) -> None:
    st.subheader("Review the competitor shortlist")
    st.write("Confirm three competitors for the selected market. You can edit the names, websites, or rationale.")
    for note in run.state.get("discovery_notes", []):
        st.warning(note)
    candidates = run.state.get("candidates", [])
    sources = {row["id"]: Source.model_validate(row) for row in run.state.get("discovery_sources", [])}
    if sources:
        with st.expander("Discovery sources"):
            for candidate in candidates:
                links = [citation(sources[key]) for key in candidate["discovery_ids"] if key in sources]
                st.markdown(f"**{escape(candidate['name'])}** · " + ", ".join(links))
            if not candidates:
                for source in sources.values():
                    st.markdown(citation(source))

    with st.form(f"shortlist_{run.checkpoint}"):
        rows = []
        for index in range(3):
            candidate = candidates[index] if index < len(candidates) else {}
            col1, col2, col3 = st.columns([1, 1, 2])
            rows.append({
                "name": col1.text_input(f"Competitor {index + 1}", candidate.get("name", ""), max_chars=100),
                "website": col2.text_input(f"Website {index + 1}", candidate.get("website", ""), max_chars=250),
                "reason": col3.text_input(f"Rationale {index + 1}", candidate.get("reason", ""), max_chars=350),
            })
        if st.form_submit_button("Confirm and research", type="primary"):
            _advance(session, run, "confirm", "Collecting and checking evidence…", rows)
    if run.state["mode"] == "live" and not run.state.get("rediscoveries") and run.state.get("discovery_notes"):
        if st.button("Retry discovery"):
            _advance(session, run, "retry", "Retrying discovery…")
    if st.button("Discard run"):
        _advance(session, run, "discard", "Discarding…")


def _briefing(run: Run) -> None:
    profiles = run.profiles
    summary = run.summary
    st.subheader("Competitor briefing")
    a, b, c = st.columns(3)
    a.metric("Competitors", summary.competitors)
    b.metric("Fields with evidence", f"{summary.covered_fields} / {summary.total_fields}")
    c.metric("Sources cited", summary.cited_pages)

    table = []
    for profile in profiles:
        table.append({
            "Competitor": profile.competitor.name,
            **{LABELS[field]: " / ".join(finding_text(profile, item) for item in findings_in(profile, field))
               or MISSING for field in FIELDS},
        })
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("Open a competitor below for readable findings, source links, and evidence excerpts.")
    for profile in profiles:
        with st.expander(profile.competitor.name):
            if profile.competitor.reason:
                st.markdown(escape(profile.competitor.reason))
            for field in FIELDS:
                st.markdown(f"**{LABELS[field]}**")
                entries = findings_in(profile, field)
                if not entries:
                    st.caption(MISSING)
                for item in entries:
                    source = source_of(profile, item)
                    st.markdown(f"{escape(finding_text(profile, item))}  \n"
                                f"{citation(source)} · {source_type(profile, source)}")
                    st.caption("Supporting excerpt")
                    st.markdown(f"> {escape(item.quote)}")
            if profile.notes:
                for note in profile.notes:
                    st.warning(note)


def _review_briefing(session: ResearchSession, run: Run) -> None:
    _briefing(run)
    if run.phase == "approved":
        st.success("Briefing approved.")
        slug = re.sub(r"[^a-z0-9]+", "-", run.state["company"]["name"].lower()).strip("-") or "research"
        stem = f"rivalscope-{slug}-{run.state['as_of']}"
        a, b, _ = st.columns([1, 1, 2])
        a.download_button("Download Markdown", report_markdown(run), f"{stem}.md", "text/markdown", on_click="ignore")
        b.download_button("Download CSV", report_csv(run).encode("utf-8-sig"), f"{stem}.csv", "text/csv", on_click="ignore")
        return

    st.info("Review the sources and any gaps before approving this briefing for download.")
    a, b, c = st.columns([1, 1, 2])
    if a.button("Approve briefing", type="primary"):
        _advance(session, run, "approve", "Recording approval…")
    if any(p.gaps for p in run.profiles) and not run.state.get("manual_pass"):
        if b.button("Retry missing evidence"):
            _advance(session, run, "retry", "Checking missing evidence…")
    if c.button("Discard briefing"):
        _advance(session, run, "discard", "Discarding…")


def research_page() -> None:
    settings = Settings.load()
    session = ResearchSession(CHECKPOINTS, settings, _id())
    run = session.status()
    st.title("RivalScope")
    if run.phase == "new":
        _start(session, settings)
        return

    with st.sidebar:
        if st.button("New research"):
            st.session_state["rivalscope_run"] = str(uuid4())
            st.query_params["run"] = st.session_state["rivalscope_run"]
            st.rerun()
        st.caption("To resume this run after closing the app, keep its URL.")

    company = run.state["company"]
    mode = "Trello demo snapshot" if run.state["mode"] == "demo" else "Live Tavily research"
    st.markdown(f"**{escape(company['name'])}** · {mode} · {run.state['as_of']}")
    if company["scope"]:
        st.caption(escape(company["scope"]))

    if run.phase == "shortlist":
        _review_shortlist(session, run)
    elif run.phase in {"briefing", "approved"}:
        _review_briefing(session, run)
    elif run.phase == "discarded":
        st.info("This run was discarded. Start new research from the sidebar.")
    elif run.phase == "interrupted":
        st.warning("The previous step stopped before it finished. You can retry from the last checkpoint.")
        if st.button("Retry from checkpoint", type="primary"):
            _advance(session, run, "retry", "Resuming research…")

    if run.state.get("events"):
        with st.expander("Research activity"):
            for event in run.state["events"]:
                st.markdown(f"- {escape(event)}")
