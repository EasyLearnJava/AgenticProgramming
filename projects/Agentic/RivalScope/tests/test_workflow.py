"""Check the boundaries a demo must survive: pause, restart, recovery, and export."""

import csv
import io
import json
from datetime import date, timedelta

import httpx
import pytest

from rivalscope import session as session_module
from rivalscope.config import Settings
from rivalscope.demo import DEMO_COMPANY
from rivalscope.models import Company
from rivalscope.reports import report_csv, report_markdown
from rivalscope.session import ResearchSession


def shortlist_rows(run):
    return [{key: row[key] for key in ("name", "website", "reason")} for row in run.state["candidates"]]


def test_demo_resumes_across_sessions_and_researches_the_gap(tmp_path):
    database = tmp_path / "runs.sqlite3"
    session = ResearchSession(database, Settings(), "demo")
    session.start(DEMO_COMPANY, "demo")
    shortlist = session.status()
    assert shortlist.phase == "shortlist"
    assert not shortlist.profiles

    reopened = ResearchSession(database, Settings(), "demo")
    rows = shortlist_rows(shortlist)
    with pytest.raises(ValueError, match="three distinct"):
        reopened.advance("shortlist", shortlist.checkpoint, "confirm", [rows[0]] * 3)
    assert reopened.status().checkpoint == shortlist.checkpoint
    reopened.advance("shortlist", shortlist.checkpoint, "confirm", rows)

    briefing = reopened.status()
    assert briefing.phase == "briefing"
    assert briefing.summary.covered_fields == 12
    with pytest.raises(ValueError, match="before exporting"):
        report_markdown(briefing)
    assert any("Targeted follow-up: ClickUp (pricing)" in event for event in briefing.state["events"])
    with pytest.raises(ValueError, match="review has changed"):
        session.advance("shortlist", shortlist.checkpoint, "confirm", rows)

    session.advance("briefing", briefing.checkpoint, "approve")
    approved = reopened.status()
    assert approved.phase == "approved"
    assert "Offline public-source snapshot" in report_markdown(approved)
    parsed = list(csv.DictReader(io.StringIO(report_csv(approved))))
    assert len(parsed) == 12
    assert {row["competitor"] for row in parsed} == {"Asana", "ClickUp", "monday.com"}
    assert all(row["source_url"].startswith("https://") for row in parsed)


def test_live_adapters_recover_from_rate_limit_and_reject_unsupported_claims(tmp_path, monkeypatch):
    searches: list[str] = []
    names = {"Alpha": "alpha.example", "Beta": "beta.example", "Gamma": "gamma.example"}
    today = date.today()

    def respond(request):
        payload = json.loads(request.content)
        if request.url.host == "api.tavily.com":
            assert request.headers["Authorization"] == "Bearer test-tavily"
            query = payload["query"]
            searches.append(query)
            if "Target" in query:
                return httpx.Response(200, json={"results": [{
                    "url": "https://research.example/alternatives",
                    "content": "Alpha, Beta, and Gamma sell tools in the same segment as Target.",
                }]})
            if query.startswith("Beta") and "official pricing" in query and searches.count(query) == 1:
                return httpx.Response(429, json={"detail": "temporary"})
            domain = names[query.split()[0]]
            field = "pricing" if "pricing" in query else "features" if "feature" in query else (
                "news" if payload.get("topic") == "news" else "positioning"
            )
            if domain == names["Gamma"] and field == "pricing":
                return httpx.Response(200, json={"results": []})
            if field == "news":
                assert payload["filter_by_published_date"]
                assert payload["start_date"] == str(today - timedelta(days=90))
            excerpts = {
                "pricing": "Standard costs $18 per month.",
                "features": "Teams can manage assignments using project boards.",
                "positioning": "The product targets small work management teams.",
                "news": "The company announced a new planning view for its product.",
            }
            return httpx.Response(200, json={"results": [{
                "url": f"https://{domain}/{field}", "content": excerpts[field],
                "published_date": str(today - timedelta(days=1 if domain != names["Gamma"] else 91)),
            }]})

        assert request.url.host == "api.tokenfactory.nebius.com"
        assert request.headers["Authorization"] == "Bearer test-nebius"
        assert payload["response_format"]["type"] == "json_object"
        inputs = json.loads(payload["messages"][1]["content"])["inputs"]
        if "target" in inputs:
            result = {"candidates": [
                {"name": name, "website": domain, "reason": "Competes for the same buyer.",
                 "discovery_ids": [inputs["sources"][0]["id"]]}
                for name, domain in names.items()
            ]}
        else:
            result = {"findings": [
                {"field": source["field"], "text": source["excerpt"].replace("$18", "$99")
                 if inputs["competitor"]["name"] == "Alpha" else source["excerpt"],
                 "source_ids": [source["id"]], "quote": source["excerpt"]}
                for source in inputs["sources"] if source["field"] != "pricing"
                or source["excerpt"].startswith("Standard")
            ][:8]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    client_type = httpx.Client
    monkeypatch.setattr(session_module.httpx, "Client", lambda **options: client_type(
        transport=httpx.MockTransport(respond), **options,
    ))
    session = ResearchSession(tmp_path / "live.sqlite3", Settings(
        tavily_key="test-tavily", nebius_key="test-nebius",
    ), "live")
    session.start(Company(name="Target"), "live")
    shortlist = session.status()
    session.advance("shortlist", shortlist.checkpoint, "confirm", shortlist_rows(shortlist))

    briefing = session.status()
    assert briefing.phase == "briefing"
    assert briefing.profiles[0].gaps == ["pricing"]  # Fabricated $99 does not pass evidence checks.
    assert briefing.profiles[1].gaps == []
    assert briefing.profiles[2].gaps == ["pricing", "news"]  # Outside the 90-day window.
    assert any(searches.count(query) == 2 for query in searches if query.startswith("Beta") and "official pricing" in query)
    assert any("Targeted follow-up" in event for event in briefing.state["events"])
    session.advance("briefing", briefing.checkpoint, "retry")
    after = session.status()
    assert after.phase == "briefing"
    assert after.summary.covered_fields == briefing.summary.covered_fields
    assert after.state["manual_pass"]
    with pytest.raises(ValueError, match="unavailable"):
        session.advance("briefing", after.checkpoint, "retry")
    session.advance("briefing", after.checkpoint, "discard")
    assert session.status().phase == "discarded"
