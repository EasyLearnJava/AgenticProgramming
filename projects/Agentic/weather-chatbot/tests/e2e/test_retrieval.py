"""A visitor runs and inspects real retrieval from Knowledge, including keyboard access and phone layouts."""

import re
from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect


def run_question(page: Page) -> None:
    """Submit a preparation question using the same fields a visitor uses."""
    page.get_by_label("Question", exact=True).fill("What clothing should I pack for cold water?")
    page.get_by_label("Park or trail", exact=True).select_option("zion-narrows")
    page.get_by_label("Visit date (optional)", exact=True).fill("2026-12-01")
    page.get_by_role("button", name="Run retrieval", exact=True).click()
    expect(page.get_by_role("heading", name="Retrieval results", exact=True)).to_be_visible(timeout=10000)
    assert "?" not in page.url
    expect(page).to_have_url(re.compile(r"/api/knowledge/retrieval$"))


def test_playground_runs_from_the_sidebar_and_links_scores_to_actual_passages(page: Page) -> None:
    page.goto("/")
    navigation = page.get_by_role("navigation", name="Main")
    navigation.get_by_role("link", name="Retrieval Playground", exact=True).click()
    expect(navigation.get_by_role("link", name="Retrieval Playground")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("heading", name="No question run yet")).to_be_visible()
    run_question(page)
    expect(page.locator("#retrieval-ranking")).to_be_visible()
    expect(page.get_by_label("Visit date (optional)", exact=True)).to_have_value("2026-12-01")
    count = page.locator(".retrieval-passage").count()
    assert 1 <= count <= 4
    row = page.locator('#retrieval-ranking tr[data-selection="retrieved"]').first
    row.get_by_role("link").click()
    expect(page).to_have_url(re.compile(r"#retrieved-"))
    page.get_by_role("link", name="Inspect chunk & vector →", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"/knowledge/chunks\?chunk="))
    expect(page.locator("#chunk-detail")).to_be_in_viewport()


@pytest.mark.parametrize("width", [1440, 360])
def test_playground_and_results_are_accessible_and_fit_the_viewport(page: Page, width: int, tmp_path: Path) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("/knowledge/retrieval")
    result = Axe().run(page)
    assert result.violations_count == 0, result.generate_report()
    run_question(page)
    page.get_by_text("How to read the scores", exact=True).click()
    result = Axe().run(page)
    assert result.violations_count == 0, result.generate_report()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(tmp_path / f"hybrid-playground-{width}.png"), full_page=True)
    page.get_by_role("link", name="Reset", exact=True).click()
    expect(page.get_by_label("Question", exact=True)).to_have_value("")
    expect(page.get_by_role("heading", name="No question run yet")).to_be_visible()


@pytest.mark.parametrize("explicit", [False, True])
def test_spring_question_uses_real_season_filter_and_explains_ranking(page: Page, explicit: bool) -> None:
    """A spring preparation request excludes winter passages without requiring an invented visit date."""
    page.goto("/knowledge/retrieval")
    page.get_by_label("Question", exact=True).fill("What should I wear to hike The Narrows in Zion in spring?")
    page.get_by_label("Park or trail", exact=True).select_option("zion-narrows")
    if explicit:
        page.get_by_label("Season (optional)", exact=True).select_option("spring")
    page.get_by_role("button", name="Run retrieval", exact=True).click()
    expect(page.get_by_role("heading", name="Retrieval results", exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_label("Visit date (optional)", exact=True)).to_have_value("")
    expect(page.locator(".retrieval-results")).to_contain_text("Season: Spring")
    expect(page.locator(".retrieval-results")).to_contain_text("selected season" if explicit else "(question)")
    expect(page.locator(".retrieval-results")).to_contain_text("Keyword terms used:")
    expect(page.locator(".retrieval-results")).to_contain_text("spring")
    expect(page.locator("#retrieval-ranking")).to_contain_text("Semantic contribution")
    expect(page.locator(".retrieval-passage h3").filter(has_text=re.compile(r"^Winter$"))).to_have_count(0)
    page.get_by_text("How to read the scores", exact=True).click()
    expect(page.locator(".retrieval-explanation")).to_contain_text("Reciprocal Rank Fusion")
    expect(page.locator(".retrieval-explanation")).to_contain_text("not correctness or confidence")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()


@pytest.mark.parametrize("base_url", ["park-hybrid"], indirect=True)
@pytest.mark.parametrize("width", [360, 1280])
def test_hosted_hybrid_explains_weights_thresholds_scope_and_missing_scores(
    page: Page, base_url: str, width: int, tmp_path: Path
) -> None:
    """Controlled hosted scores prove this browser path uses hosted provenance and the actual fusion policy."""
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(base_url)
    expect(page.locator(".chat-privacy")).to_contain_text("Park guidance search terms go to Qdrant")
    page.goto(f"{base_url}/knowledge/retrieval")
    page.get_by_label("Question", exact=True).fill("What should I wear to hike The Narrows in Zion in spring?")
    page.get_by_label("Park or trail", exact=True).select_option("zion-narrows")
    page.get_by_label("Season (optional)", exact=True).select_option("spring")
    page.get_by_role("button", name="Run retrieval", exact=True).click()
    results = page.locator(".retrieval-results")
    expect(results).to_have_attribute("data-retrieval-mode", "hybrid")
    expect(results).to_contain_text("Qdrant Cloud MiniLM")
    expect(results).to_contain_text("sentence-transformers/all-minilm-l6-v2")
    expect(results).to_contain_text("Season: Spring (selected season)")
    expect(results).to_contain_text("Keyword provider: Qdrant BM25")
    expect(results).to_contain_text("same hosted semantic vectors")
    expect(results).not_to_contain_text("separately built local index")
    scores = page.locator("#retrieval-ranking td.retrieval-score")
    expect(scores.filter(has_text="0.8400")).to_have_count(1)
    expect(scores.filter(has_text="Not returned").first).to_be_visible()
    expect(page.locator(".retrieval-passage h3").filter(has_text=re.compile(r"^Winter$"))).to_have_count(0)
    page.get_by_text("How to read the scores", exact=True).click()
    explanation = page.locator(".retrieval-explanation")
    expect(explanation).to_contain_text("1.0 / (60 + rank)")
    expect(explanation).to_contain_text("0.1 / (60 + rank)")
    expect(explanation).to_contain_text("Semantic ranking starts at 0.3")
    expect(explanation).to_contain_text("semantic similarity of at least 0.55")
    expect(explanation).to_contain_text("not correctness or confidence")
    assert "?" not in page.url
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    results.evaluate("element => element.scrollIntoView({block: 'start'})")
    page.screenshot(path=str(tmp_path / f"hosted-playground-{width}.png"))
    explanation.screenshot(path=str(tmp_path / f"hosted-scoring-{width}.png"))


@pytest.mark.parametrize(
    ("base_url", "expected_status"),
    [("park-rerank", "ready"), ("park-rerank-error", "unavailable")],
    indirect=["base_url"],
)
@pytest.mark.parametrize("width", [360, 1280])
def test_colbert_final_order_or_rrf_fallback_is_visible_and_accessible(
    page: Page, base_url: str, width: int, tmp_path: Path, expected_status: str
) -> None:
    """Controlled reranking proves final context order, score labels and truthful failure on phones and desktops."""
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{base_url}/knowledge/retrieval")
    page.get_by_label("Question", exact=True).fill("What should I wear to hike The Narrows in Zion in spring?")
    page.get_by_label("Park or trail", exact=True).select_option("zion-narrows")
    page.get_by_role("button", name="Run retrieval", exact=True).click()
    results = page.locator(".retrieval-results")
    expect(results).to_have_attribute("data-rerank-status", expected_status)
    ranked = page.locator('#retrieval-ranking tr[data-selection="retrieved"]')
    first = ranked.first
    rrf = first.locator(".retrieval-score").nth(4)
    rerank = first.locator(".retrieval-rerank-score")
    if expected_status == "ready":
        expect(results).to_contain_text("ColBERT reranked the RRF shortlist")
        expect(rrf.locator(".retrieval-branch-rank")).not_to_have_text("Rank 1")
        expect(rerank.locator(".retrieval-branch-rank")).to_have_text("Rank 1")
        assert float(rerank.locator("strong").inner_text()) > 1  # ColBERT is not cosine similarity.
    else:
        expect(results).to_have_attribute("data-rerank-status", "unavailable")
        expect(results).to_contain_text("Final order keeps the original RRF ranking")
        expect(rrf.locator(".retrieval-branch-rank")).to_have_text("Rank 1")
        expect(rerank).to_contain_text("Not reranked")
    assert ranked.evaluate_all("rows => rows.map(row => 'retrieved-' + row.dataset.chunk)") == (
        page.locator(".retrieval-passage").evaluate_all("rows => rows.map(row => row.id)")
    )
    page.get_by_text("How to read the scores", exact=True).click()
    expect(page.locator(".retrieval-explanation")).to_contain_text("not probabilities or confidence")
    assert "?" not in page.url
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    results.screenshot(path=str(tmp_path / f"colbert-playground-{width}.png"))
