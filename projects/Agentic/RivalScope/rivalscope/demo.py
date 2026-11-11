"""Frozen public-source snapshot for running the actual workflow without keys."""

from datetime import date

from .agents import grounded_findings
from .models import Candidate, Company, FieldName, Finding, Profile, Source

DEMO_DATE = date(2026, 11, 10)
DEMO_COMPANY = Company(name="Trello", website="trello.com", scope="US work management for small teams")

# Excerpts below are compact, hand-curated summaries of the linked pages.
# In live mode they are Tavily's actual excerpts, supplied through the same Source record.
DEMO_ROWS = {
    "Asana": (
        "asana.com", "Its task boards compete for teams managing recurring projects.",
        {
            "pricing": ("https://asana.com/pricing", "Asana plans",
                        "Starter is listed at $10.99 per user per month, billed annually.", None),
            "features": ("https://asana.com/pricing", "Asana plan features",
                         "Personal offers list, board and calendar views. Starter adds Timeline and Gantt views.", None),
            "positioning": ("https://asana.com/pricing", "Asana plan audiences",
                            "Asana markets Starter to small teams and professionals who track projects and deadlines.", None),
            "news": ("https://asana.com/inside-asana/asana-q3-2026-release-ai-teammates", "Asana Q3 product release",
                     "Asana announced its Q3 product release with AI capabilities built into team workflows.", "2026-10-22"),
        },
    ),
    "ClickUp": (
        "clickup.com", "Its Kanban boards overlap with Trello, alongside documents and sprint management.",
        {
            "pricing": ("https://clickup.com/pricing", "ClickUp plans",
                        "The pricing page lists the Free Forever plan at $0.", None),
            "features": ("https://clickup.com/pricing", "ClickUp plan features",
                         "Free Forever includes Kanban boards, collaborative documents, calendar view and sprint management.", None),
            "positioning": ("https://clickup.com/", "ClickUp product overview",
                            "ClickUp presents tasks, documents and other collaboration tools as one workspace.", None),
            "news": ("https://feedback.clickup.com/changelog/release-notes-409", "ClickUp release notes 4.09",
                     "ClickUp 4.09 added automated creation of lists from templates and personal time off in workload views.",
                     "2026-10-17"),
        },
    ),
    "monday.com": (
        "monday.com", "Custom boards address similar work tracking needs for teams that want configurable workflows.",
        {
            "pricing": ("https://monday.com/pricing", "monday.com plans",
                        "The displayed 10-seat annual Basic configuration lists $9 per seat per month.", None),
            "features": ("https://monday.com/pricing", "monday.com plan features",
                         "Boards support configurable column types. Standard adds workflow automations.", None),
            "positioning": ("https://monday.com/w/use-cases/ai-project-management-software", "monday work management",
                            "monday work management targets teams that coordinate projects and processes across functions.", None),
            "news": ("https://monday.com/newsroom/announcements/q3-2026-results", "monday.com Q3 results",
                     "monday.com announced its third-quarter 2026 results.", "2026-11-09"),
        },
    ),
}


class DemoResearch:
    def discover(self, company: Company, as_of: date) -> tuple[list[Candidate], list[Source], list[str]]:
        candidates, sources = [], []
        for name, (domain, reason, fields) in DEMO_ROWS.items():
            url, title, excerpt, _ = fields["features"]
            source = Source(id=f"demo:{domain}:discovery", url=url, title=title,
                            excerpt=excerpt, field="discovery", retrieved=as_of)
            candidates.append(Candidate(name=name, website=domain, reason=reason, discovery_ids=[source.id]))
            sources.append(source)
        return candidates, sources, []

    def gather(
        self, company: Company, competitor: Candidate, as_of: date,
        fields: tuple[FieldName, ...], *, follow_up: bool,
    ) -> tuple[list[Source], list[str], bool]:
        sources = []
        match = next((row for name, row in DEMO_ROWS.items()
                      if name.casefold() == competitor.name.casefold() and row[0] == competitor.website), None)
        if not match:
            return [], ["This edited competitor is outside the offline snapshot. Use Live mode for fresh evidence."], True
        domain, _, rows = match
        for field in fields:
            # Simulate one missing result so the offline demo exercises the real gap routing.
            if domain == "clickup.com" and field == "pricing" and not follow_up:
                continue
            url, title, excerpt, published = rows[field]
            sources.append(Source(id=f"demo:{domain}:{field}", url=url, title=title,
                                  excerpt=excerpt, field=field, retrieved=as_of, published=published))
        return sources, [], False

    def analyze(self, profile: Profile, as_of: date) -> list[Finding]:
        proposed = [
            Finding(field=source.field, text=source.excerpt, quote=source.excerpt, source_ids=[source.id])
            for source in profile.sources
        ]
        return grounded_findings(proposed, profile.sources, as_of)
