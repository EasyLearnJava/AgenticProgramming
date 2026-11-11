"""Discovery, evidence gathering, and evidence-constrained analysis."""

import re
from datetime import date, timedelta

from pydantic import Field

from . import prompts
from .models import (
    FIELDS, NEWS_DAYS, Candidate, Company, FieldName, Finding, Profile, Record, Source, one_line,
)
from .providers import Nebius, ProviderError, Tavily

QUERIES = {
    "pricing": "official pricing plans cost subscription",
    "features": "product documentation core features workflows",
    "positioning": "product intended customers use cases market positioning",
    "news": "company product launches releases announcements",
}
FOLLOW_UP = {
    "pricing": "price plans pricing page free tier per user subscription",
    "features": "product help center feature overview",
    "positioning": "company product buyers target teams customers about",
    "news": "recent official press release product changelog",
}


class Shortlist(Record):
    candidates: list[Candidate] = Field(max_length=3)


class Extraction(Record):
    findings: list[Finding] = Field(max_length=8)


def unique_sources(items: list[Source]) -> list[Source]:
    return list({item.id: item for item in items}.values())


def source_context(sources: list[Source]) -> list[dict]:
    return [source.model_dump(mode="json", exclude={"retrieved"}) for source in sources]


def grounded_findings(
    findings: list[Finding], sources: list[Source], as_of: date,
) -> list[Finding]:
    """Accept only a known same-field source and a quote present in its excerpt."""
    by_id = {source.id: source for source in sources}
    accepted: list[Finding] = []
    for finding in findings:
        # Each claim has one quote, so it gets exactly one evidence source.
        if len(finding.source_ids) != 1:
            continue
        source = by_id.get(finding.source_ids[0])
        quote = one_line(finding.quote).casefold()
        if not source or source.field != finding.field or len(quote) < 12:
            continue
        if quote not in one_line(source.excerpt).casefold():
            continue
        if finding.field == "pricing":
            # Prevent invented amounts; compare numbers as written rather than rounding them.
            numbers = r"\d+(?:[.,]\d+)*"
            if not set(re.findall(numbers, finding.text)) <= set(re.findall(numbers, quote)):
                continue
        if finding.field == "news":
            if not source.published or not as_of - timedelta(days=NEWS_DAYS) <= source.published <= as_of:
                continue
        same_field = [item for item in accepted if item.field == finding.field]
        if len(same_field) < 2 and all(item.text.casefold() != finding.text.casefold() for item in same_field):
            accepted.append(finding)
    return accepted


class LiveResearch:
    def __init__(self, tavily: Tavily, model: Nebius):
        self.tavily = tavily
        self.model = model

    def discover(self, company: Company, as_of: date) -> tuple[list[Candidate], list[Source], list[str]]:
        target = " ".join(filter(None, (company.name, company.website, company.scope)))
        evidence: list[Source] = []
        notes: list[str] = []
        for query in (f"{target} direct competitors alternatives", f"{target} product comparisons similar tools"):
            try:
                evidence.extend(self.tavily.search(query, "discovery", as_of))
            except ProviderError as error:
                notes.append(str(error))
                if error.permanent:
                    break
        evidence = unique_sources(evidence)
        if not evidence:
            return [], [], notes or ["Discovery found no relevant search results."]

        try:
            result = self.model.generate(prompts.DISCOVERY, {
                "target": company.model_dump(), "sources": source_context(evidence),
            }, Shortlist)
        except ProviderError as error:
            return [], evidence, [*notes, str(error)]

        source_ids = {source.id for source in evidence}
        candidates: list[Candidate] = []
        used_names = {company.name.casefold()}
        used_domains = {company.website} if company.website else set()
        for candidate in result.candidates:
            name = candidate.name.casefold()
            ids = [value for value in candidate.discovery_ids if value in source_ids]
            if not ids or name in used_names or (candidate.website and candidate.website in used_domains):
                continue
            candidates.append(candidate.model_copy(update={"discovery_ids": list(dict.fromkeys(ids))}))
            used_names.add(name)
            if candidate.website:
                used_domains.add(candidate.website)
        if len(candidates) < 3:
            notes.append("Discovery could not support three distinct candidates. Fill any gaps before continuing.")
        return candidates, evidence, notes

    def gather(
        self, company: Company, competitor: Candidate, as_of: date,
        fields: tuple[FieldName, ...], *, follow_up: bool,
    ) -> tuple[list[Source], list[str], bool]:
        evidence: list[Source] = []
        notes: list[str] = []
        query_plan = FOLLOW_UP if follow_up else QUERIES
        for field in fields:
            # The first pricing query searches the reviewed domain. A gap can widen it.
            domain = competitor.website if field == "pricing" and not follow_up else ""
            query = " ".join(filter(None, (competitor.name, competitor.website, query_plan[field], company.scope)))
            try:
                evidence.extend(self.tavily.search(query, field, as_of, domain=domain))
            except ProviderError as error:
                notes.append(f"{field.title()}: {error}")
                if error.permanent:
                    return evidence, notes, True
        return evidence, notes, False

    def analyze(self, profile: Profile, as_of: date) -> list[Finding]:
        if not profile.sources:
            return []
        result = self.model.generate(prompts.EXTRACTION, {
            "competitor": profile.competitor.model_dump(exclude={"discovery_ids", "reason"}),
            "research_date": as_of.isoformat(),
            "news_window_days": NEWS_DAYS,
            "sources": source_context(profile.sources),
        }, Extraction)
        return grounded_findings(result.findings, profile.sources, as_of)


def merge_findings(previous: list[Finding], new: list[Finding]) -> list[Finding]:
    """Keep earlier supported findings if the follow-up returns fewer results."""
    combined = list(previous)
    for item in new:
        same_field = [finding for finding in combined if finding.field == item.field]
        if len(same_field) < 2 and all(finding.text.casefold() != item.text.casefold() for finding in same_field):
            combined.append(item)
    return combined
