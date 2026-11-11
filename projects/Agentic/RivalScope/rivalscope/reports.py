"""One briefing structure for the app, Markdown export, and CSV export."""

import csv
import html
import io
import re
from urllib.parse import urlsplit

from .models import FIELDS, LABELS, NEWS_DAYS, FieldName, Finding, Profile, Source
from .session import Run

MISSING = "No supported finding"


def escape(text: str) -> str:
    """Show externally supplied text as text in Markdown and Streamlit."""
    return re.sub(r"([\\`*_{}\[\]()#+.!|$~])", r"\\\1", html.escape(text, quote=False))


def citation(source: Source, label: str | None = None) -> str:
    return f"[{escape(label or source.title)}](<{source.url}>)"


def source_of(profile: Profile, finding: Finding) -> Source:
    return next(source for source in profile.sources if source.id == finding.source_ids[0])


def source_type(profile: Profile, source: Source) -> str:
    domain = profile.competitor.website
    host = urlsplit(source.url).hostname or ""
    if domain and (host == domain or host.endswith("." + domain)):
        return "Company source"
    return "External source"


def findings_in(profile: Profile, field: FieldName) -> list[Finding]:
    return [finding for finding in profile.findings if finding.field == field]


def finding_text(profile: Profile, finding: Finding) -> str:
    source = source_of(profile, finding)
    if finding.field == "news" and source.published:
        return f"{source.published}: {finding.text}"
    return finding.text


def report_markdown(run: Run) -> str:
    if run.phase != "approved":
        raise ValueError("Approve the briefing before exporting it.")
    state, profiles = run.state, run.profiles
    company = state["company"]
    mode = "Offline public-source snapshot" if state["mode"] == "demo" else "Live Tavily research"
    lines = [
        f"# RivalScope briefing · {escape(company['name'])}", "",
        f"Research date: {state['as_of']}  ",
        f"Evidence mode: {mode}  ",
        f"Scope: {escape(company['scope'] or 'No additional scope')}  ",
        f"Coverage: {run.summary.covered_fields} of {run.summary.total_fields} research fields  ",
        f"News window: {NEWS_DAYS} days through the research date", "",
        "## Competitor comparison", "",
        "| Competitor | Pricing | Core features | Market positioning | Recent news |",
        "| --- | --- | --- | --- | --- |",
    ]
    for profile in profiles:
        cells = [escape(profile.competitor.name)]
        for field in FIELDS:
            entries = findings_in(profile, field)
            cells.append(" / ".join(escape(finding_text(profile, item)) for item in entries) or MISSING)
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(["", "## Findings and sources", ""])
    discovery = {row["id"]: Source.model_validate(row) for row in state.get("discovery_sources", [])}
    for profile in profiles:
        competitor = profile.competitor
        lines.extend([f"### {escape(competitor.name)}", ""])
        if competitor.website:
            lines.extend([f"Reviewed website: {escape(competitor.website)}", ""])
        if competitor.reason:
            proof = ", ".join(citation(discovery[key]) for key in competitor.discovery_ids if key in discovery)
            lines.extend([f"Shortlist rationale: {escape(competitor.reason)}" + (f" ({proof})" if proof else ""), ""])
        for field in FIELDS:
            lines.append(f"**{LABELS[field]}**")
            lines.append("")
            items = findings_in(profile, field)
            for item in items:
                source = source_of(profile, item)
                lines.append(f"- {escape(finding_text(profile, item))} — {citation(source)} "
                             f"({source_type(profile, source)}, accessed {source.retrieved})")
            if not items:
                lines.append(f"- {MISSING}.")
            lines.append("")
        if profile.notes:
            lines.extend(["Research notes", "", *[f"- {escape(note)}" for note in profile.notes], ""])
    return "\n".join(lines).rstrip() + "\n"


def _csv_cell(value: str) -> str:
    # Prevent spreadsheet formula execution if a user or search snippet starts with a trigger.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def report_csv(run: Run) -> str:
    if run.phase != "approved":
        raise ValueError("Approve the briefing before exporting it.")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("target", "competitor", "field", "status", "finding", "source_url",
                     "source_type", "published_date", "research_date", "mode"))
    for profile in run.profiles:
        for field in FIELDS:
            entries = findings_in(profile, field)
            for entry in entries or [None]:
                source = source_of(profile, entry) if entry else None
                row = (
                    run.state["company"]["name"], profile.competitor.name, LABELS[field],
                    "Supported" if entry else "Gap", entry.text if entry else "",
                    source.url if source else "", source_type(profile, source) if source else "",
                    str(source.published) if source and source.published else "",
                    run.state["as_of"], run.state["mode"],
                )
                writer.writerow([_csv_cell(value) for value in row])
    return output.getvalue()
