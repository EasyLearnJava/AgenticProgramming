"""
tests/unit/test_docs.py: the documentation: every published page has its file, the Markdown renders as
text and links only, and GitHub-style links and pictures become the app's own addresses.
"""

import re

import pytest
from fastapi.testclient import TestClient

from nimbus.constants import DOCS_DIR, DOCS_IMAGES_DIR
from nimbus.docs import (
    ALL_DOCS,
    CHAPTERS,
    DocPage,
    find_doc,
    read_markdown,
    render_markdown,
    title_of,
    to_app_url,
    to_image_url,
)


def test_only_current_documentation_files_have_public_pages() -> None:
    assert {path.stem for path in DOCS_DIR.glob("*.md") if not path.stem.endswith("_deprecated")} == set(ALL_DOCS)


@pytest.mark.parametrize("slug", sorted(ALL_DOCS))
def test_every_page_has_a_title(slug: str) -> None:
    assert title_of(read_markdown(slug)) != ""


@pytest.mark.parametrize("slug", sorted(ALL_DOCS))
def test_no_page_holds_an_invisible_line_separator(slug: str) -> None:
    # U+2028 and U+2029 don't show on the screen, and a tool can write one where an escape was meant (issue 26).
    assert not {chr(0x2028), chr(0x2029)} & set(read_markdown(slug))


@pytest.mark.parametrize("slug", sorted(ALL_DOCS))
def test_no_document_links_to_a_retired_app_page(slug: str) -> None:
    hrefs = re.findall(r'<a href="([^"]+)"', render_markdown(read_markdown(slug)))
    assert not [href for href in hrefs if "_deprecated" in href and "://" not in href]


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("step-1.md", "/docs/step-1"),
        ("issues.md", "/issues"),
        ("issues.md#step-1", "/issues#step-1"),
        ("unknown.md", "unknown.md"),
        ("https://example.com/step-1.md", "https://example.com/step-1.md"),
        ("#top", "#top"),
        ("../README.md", "../README.md"),
        ("images/demo-day-cache-flow.svg", "/docs/images/demo-day-cache-flow.svg"),
    ],
)
def test_a_github_link_becomes_the_apps_own_address(href: str, expected: str) -> None:
    assert to_app_url(href) == expected


def test_a_picture_beside_the_docs_is_served_under_docs_images() -> None:
    assert to_image_url("images/step-1.svg") == "/docs/images/step-1.svg"
    assert to_image_url("https://example.com/x.png") == "https://example.com/x.png"


def test_raw_html_is_shown_as_text_never_rendered() -> None:
    html = render_markdown("<script>alert(1)</script>\n\nA <b>bold</b> word.")
    assert "<script>" not in html
    assert "<b>" not in html
    assert "&lt;script&gt;" in html


def test_a_script_address_never_becomes_a_link() -> None:
    assert 'href="javascript' not in render_markdown("[click](javascript:alert(1))")


def test_renders_tables() -> None:
    assert "<table>" in render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")


def test_an_aligned_column_gets_a_class_never_an_inline_style_the_policy_refuses() -> None:
    html = render_markdown("| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |")
    assert "style=" not in html
    assert '<th class="align-left">a</th>' in html
    assert '<td class="align-center">2</td>' in html
    assert '<td class="align-right">3</td>' in html


def test_the_system_design_shows_its_own_diagram() -> None:
    html = render_markdown(read_markdown("system-design"))
    assert 'src="/docs/images/system-design.svg"' in html
    assert (DOCS_IMAGES_DIR / "system-design.svg").is_file()


def test_demo_day_shows_its_diagram_and_opens_it_full_size(client: TestClient) -> None:
    # The page's <main> names it, so only DemoDay gets its own look; the diagram links to itself, full size.
    html = client.get("/demo-day").text
    assert '<main class="doc" data-doc="demo-day">' in html
    assert '<a href="/docs/images/demo-day-cache-flow.svg"><img src="/docs/images/demo-day-cache-flow.svg"' in html
    assert (DOCS_IMAGES_DIR / "demo-day-cache-flow.svg").is_file()
    assert client.get("/docs/images/demo-day-cache-flow.svg").status_code == 200
    assert '<main class="doc" data-doc="architecture">' in client.get("/architecture").text


def test_finds_a_page_only_by_its_own_address() -> None:
    assert find_doc("/docs/step-1") == CHAPTERS[0]
    assert find_doc("/issues_deprecated") is None
    assert find_doc("/docs/issues") is None
    assert find_doc("/docs/../../etc/passwd") is None


def _section(markdown: str, heading: str) -> str:
    """The text under a "## " heading, up to the next one."""
    start = markdown.index(f"\n## {heading}\n") + len(heading) + 5
    end = markdown.find("\n## ", start)
    return markdown[start : end if end != -1 else None].strip()


@pytest.mark.parametrize("doc", CHAPTERS, ids=lambda doc: doc.slug)
def test_the_interview_guide_has_each_chapters_questions_word_for_word(doc: DocPage) -> None:
    chapter = read_markdown(doc.slug)
    assert _section(read_markdown("interview"), title_of(chapter)) == _section(chapter, "Interview questions")


def test_a_title_is_the_first_heading() -> None:
    assert title_of("intro\n# First\n# Second") == "First"
    assert title_of("no heading") == ""
