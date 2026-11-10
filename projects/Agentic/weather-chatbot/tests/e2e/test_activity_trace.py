"""Explore safe trace call trees, filters, timings and errors using Chrome, keyboard and mobile layouts."""

from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.parametrize("base_url", ["trace"], indirect=True)


@pytest.mark.parametrize(
    ("ref", "operation", "outcome"),
    [
        ("55555555", "read", "Completed"),
        ("66666666", "save", "Completed"),
        ("77777777", "delete", "Failed"),
    ],
)
def test_memory_operation_opens_its_private_content_free_trace(
    page: Page,
    base_url: str,
    ref: str,
    operation: str,
    outcome: str,
    tmp_path: Path,
) -> None:
    """Read, save and unconfirmed delete traces work without a model call, including mobile accessibility."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{base_url}/activity?show=memory")
    request = page.locator("details.obs-details").filter(has_text=f"Ref {ref}")
    request.locator("summary").click()
    expect(request).not_to_contain_text("No linked LangSmith trace")
    request.locator('a[href^="/activity/trace/"]').click()
    expect(page.locator(".trace-row")).to_have_count(1)
    expect(page.locator(".trace-row")).to_contain_text(f"Mem0 {operation}")
    expect(page.locator(".trace-row")).to_contain_text(outcome)
    expect(page.locator(".trace-metric").filter(has_text="Trace duration")).to_contain_text("145 ms")
    expect(page.locator(".trace-metric").filter(has_text="Memory operations")).to_contain_text("1")
    expect(page.locator(".trace-metric").filter(has_text="Model calls")).to_contain_text("0")
    page.get_by_role("button", name="Memory", exact=True).click()
    page.locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-parent]")).to_have_text("None (trace root)")
    expect(page.locator(".trace-privacy-note")).to_contain_text("preference values, identities and keys stay private")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    page.screenshot(path=str(tmp_path / f"mem0-trace-{operation}.png"), full_page=True)


@pytest.mark.parametrize("width", [360, 1280])
def test_activity_opens_its_own_trace_with_model_tool_timings_and_error(
    page: Page, base_url: str, width: int, tmp_path: Path
) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref 11111111")
    request.locator("summary").focus()
    page.keyboard.press("Enter")
    trace = request.get_by_role("link", name="View LangSmith trace for request 11111111")
    expect(trace).to_be_visible()
    assert not any("/activity/trace/" in url for url in seen)
    trace.press("Enter")
    expect(page.get_by_role("heading", level=1, name="LangSmith trace")).to_be_visible()
    assert page.url.startswith(f"{base_url}/activity/trace/")
    expect(page.get_by_role("navigation", name="Main").get_by_role("link", name="Activity")).to_have_attribute(
        "aria-current", "page"
    )
    timeline = page.get_by_role("table", name="Call timeline")
    model = timeline.get_by_role("row").filter(has_text="Gemini")
    for part in ("Model", "+30 ms", "880 ms", "Completed"):
        expect(model).to_contain_text(part)
    tool = timeline.get_by_role("row").filter(has_text="get_forecast").first
    for part in ("Tool", "+920 ms", "12 ms", "Failed", "Tool call failed"):
        expect(tool).to_contain_text(part)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    page.screenshot(path=str(tmp_path / f"trace-{width}.png"), full_page=True)
    page.get_by_role("link", name="Back to Activity").click()
    expect(page).to_have_url(f"{base_url}/activity")


def open_ready_trace(page: Page, base_url: str) -> None:
    """Follow the same signed, on-demand trace link that an Activity visitor opens."""
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref 11111111")
    request.locator("summary").click()
    request.get_by_role("link", name="View LangSmith trace for request 11111111").click()
    expect(page.get_by_role("heading", name="LangSmith trace", exact=True)).to_be_visible()


def test_tree_collapse_and_filters_preserve_context_without_network_requests(page: Page, base_url: str) -> None:
    open_ready_trace(page, base_url)
    calls: list[str] = []
    page.on("request", lambda request: calls.append(request.url))
    rows = page.locator(".trace-row")
    expect(rows).to_have_count(4)
    toggles = page.locator("[data-trace-toggle]")
    toggles.first.focus()
    page.keyboard.press("Enter")
    expect(toggles.first).to_have_attribute("aria-expanded", "false")
    expect(page.locator(".trace-row:visible")).to_have_count(1)
    toggles.first.press("Enter")
    expect(page.locator(".trace-row:visible")).to_have_count(4)
    toggles.nth(1).click()
    expect(page.locator(".trace-row:visible")).to_have_count(3)
    page.locator('[data-trace-filter="model"]').click()
    expect(page.locator(".trace-row:visible")).to_have_count(2)
    expect(page.locator(".trace-row:visible").last).to_contain_text("Gemini")
    page.locator('[data-trace-filter="failed"]').click()
    expect(page.locator(".trace-row:visible")).to_have_count(3)
    expect(page.locator(".trace-row:visible").last).to_contain_text("get_forecast")
    assert calls == []
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()


def test_call_inspector_search_and_keyboard_selection(page: Page, base_url: str) -> None:
    open_ready_trace(page, base_url)
    select = page.locator("[data-trace-select]").last
    select.focus()
    page.keyboard.press("Enter")
    inspector = page.locator("[data-trace-inspector]")
    expect(inspector).to_contain_text("get_forecast")
    expect(inspector).to_contain_text("10 ms")
    expect(inspector).to_contain_text("921 ms")
    expect(inspector).to_contain_text("Tool call failed")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    page.locator("#trace-search").fill("nothing-matches-this-call")
    expect(page.locator(".trace-row:visible")).to_have_count(0)
    expect(page.get_by_text("No matching calls", exact=False)).to_be_visible()
    page.locator("#trace-search").fill("Gemini")
    expect(page.locator(".trace-row:visible")).to_have_count(2)
    page.locator("#trace-search").clear()
    expect(page.locator(".trace-row:visible")).to_have_count(4)


def test_trace_remains_readable_without_javascript(browser: Browser, base_url: str) -> None:
    with browser.new_context(java_script_enabled=False) as context:
        page = context.new_page()
        open_ready_trace(page, base_url)
        expect(page.locator(".trace-row:visible")).to_have_count(4)
        expect(page.get_by_role("table", name="Call timeline")).to_contain_text("Tool call failed")
        expect(page.get_by_role("link", name="Refresh trace")).to_be_visible()


def test_partial_trace_keeps_missing_ancestry_and_timings_explicit(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref 44444444")
    request.locator("summary").click()
    request.get_by_role("link", name="View LangSmith trace for request 44444444").click()
    page.locator("[data-trace-select]").last.click()
    expect(page.locator("[data-trace-detail-parent]")).to_have_text("Not available in this view")
    expect(page.locator("[data-trace-detail-duration]")).to_have_text("Unknown")
    expect(page.locator("[data-trace-detail-status]")).to_have_text("Running")
    expect(page.get_by_text("Additional calls were omitted", exact=False)).to_be_visible()


def test_pending_trace_can_be_refreshed_and_legacy_request_has_no_trace_link(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/activity")
    legacy = page.locator("details.obs-details").filter(has_text="Ref 33333333")
    legacy.locator("summary").click()
    expect(legacy.get_by_text("No linked LangSmith trace for this request.")).to_be_visible()
    expect(legacy.get_by_role("link")).to_have_count(0)
    pending = page.locator("details.obs-details").filter(has_text="Ref 22222222")
    pending.locator("summary").click()
    pending.get_by_role("link", name="View LangSmith trace for request 22222222").click()
    expect(page.get_by_role("note")).to_contain_text("no visible calls")
    same_trace = page.url
    page.get_by_role("link", name="Refresh trace").click()
    expect(page).to_have_url(same_trace)
    expect(page.get_by_role("note")).to_contain_text("no visible calls")


@pytest.mark.parametrize("width", [360, 1280])
def test_qdrant_outcomes_scores_and_failed_save_are_visible(
    page: Page, base_url: str, width: int, tmp_path: Path
) -> None:
    """Cache operations retain their nesting and explain results without inflating model or tool counts."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref 88888888")
    request.locator("summary").click()
    request.get_by_role("link", name="View LangSmith trace for request 88888888").click()
    expect(page.locator(".trace-row")).to_have_count(8)
    expect(page.locator(".trace-metric").filter(has_text="Model calls")).to_contain_text("0")
    expect(page.locator(".trace-metric").filter(has_text="Tool spans")).to_contain_text("0")
    similarity = page.locator(".trace-row").filter(has_text="Qdrant similarity search")
    expect(similarity).to_contain_text("Miss")
    expect(similarity).to_contain_text("0.762")
    similarity.locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-outcome]")).to_have_text("Miss")
    expect(page.locator("[data-trace-detail-score]")).to_have_text("0.762")
    expect(page.locator("[data-trace-detail-threshold]")).to_have_text("0.800")
    expect(page.locator("[data-trace-detail-parent]")).to_have_text("Weather answer cache lookup")
    expect(page.locator("[data-trace-score-note]")).to_be_visible()
    page.screenshot(path=str(tmp_path / f"cache-trace-{width}.png"), full_page=True)
    page.locator(".trace-row").filter(has_text="Qdrant save").locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-outcome]")).to_have_text("Error")
    expect(page.locator("[data-trace-detail-status]")).to_have_text("Failed")
    expect(page.locator("[data-trace-field='score']")).to_be_hidden()
    expect(page.locator("[data-trace-score-note]")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()


def test_qdrant_bypass_reason_is_shown_without_a_cache_call(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref 99999999")
    request.locator("summary").click()
    request.get_by_role("link", name="View LangSmith trace for request 99999999").click()
    expect(page.locator(".trace-row")).to_have_count(1)
    page.locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-outcome]")).to_have_text("Bypassed")
    expect(page.locator("[data-trace-detail-cacheReason]")).to_have_text("Conversation could not be verified")
    expect(page.locator("[data-trace-field='score']")).to_be_hidden()


@pytest.mark.parametrize("width", [360, 1280])
def test_park_retrieval_mode_and_failed_semantic_fallback_are_clear(
    page: Page, base_url: str, width: int, tmp_path: Path
) -> None:
    """Park traces show operational evidence while keeping fallback success distinct from a failed stage."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref aaaaaaaa")
    request.locator("summary").click()
    request.get_by_role("link", name="View LangSmith trace for request aaaaaaaa").click()
    expect(page.locator(".trace-row")).to_have_count(6)
    expect(page.locator(".trace-metric-primary")).to_contain_text("350 ms")
    expect(page.locator(".trace-metric-primary")).to_contain_text("Completed")
    expect(page.locator(".trace-metric").filter(has_text="Model calls")).to_contain_text("0")
    expect(page.locator("[data-trace-detail-retrievalMode]")).to_have_text("BM25 only")
    expect(page.locator("[data-trace-detail-retrievalProvider]")).to_have_text("Qdrant Cloud")
    expect(page.locator("[data-trace-detail-retrievalCandidates]")).to_have_text("12")
    expect(page.locator("[data-trace-detail-retrievalSelected]")).to_have_text("4")
    expect(page.locator("[data-trace-detail-retrievalSeasonSource]")).to_have_text("Question")
    collection = page.locator(".trace-row").filter(has_text="Qdrant park collection read")
    expect(collection).to_have_count(1)
    keyword = page.locator(".trace-row").filter(has_text="Qdrant park BM25 search")
    keyword.locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-status]")).to_have_text("Completed")
    expect(page.locator("[data-trace-detail-retrievalProvider]")).to_have_text("Qdrant Cloud")
    semantic = page.locator(".trace-row").filter(has_text="Qdrant park semantic search")
    semantic.locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-outcome]")).to_have_text("Index version mismatch")
    expect(page.locator("[data-trace-detail-status]")).to_have_text("Failed")
    expect(page.locator("[data-trace-detail-parent]")).to_have_text("Park guidance retrieval")
    expect(page.locator("[data-trace-field='retrievalCandidates']")).to_be_hidden()
    rerank = page.locator(".trace-row").filter(has_text="Qdrant ColBERT rerank")
    rerank.locator("[data-trace-select]").click()
    expect(page.locator("[data-trace-detail-outcome]")).to_have_text("Invalid response")
    expect(page.locator("[data-trace-detail-status]")).to_have_text("Failed")
    expect(page.locator("[data-trace-detail-parent]")).to_have_text("Park guidance retrieval")
    expect(page.locator("[data-trace-detail-retrievalCandidates]")).to_have_text("12")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    page.screenshot(path=str(tmp_path / f"park-trace-{width}.png"), full_page=True)
