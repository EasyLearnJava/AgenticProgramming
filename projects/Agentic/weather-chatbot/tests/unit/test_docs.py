"""
tests/unit/test_docs.py: the documentation: every page has its file and every file its page, the Markdown renders as
text and links only, and GitHub-style links and pictures become the app's own addresses.
"""

import pytest

from nimbus.constants import DOCS_DIR, DOCS_IMAGES_DIR
from nimbus.docs import (
    ALL_DOCS,
    CHAPTERS,
    DEPRECATED_PAGES,
    DEPRECATED_STEPS,
    DocPage,
    find_doc,
    read_markdown,
    render_markdown,
    title_of,
    to_app_url,
    to_image_url,
)


def test_every_page_has_its_file_and_every_file_its_page() -> None:
    assert {path.stem for path in DOCS_DIR.glob("*.md")} == set(ALL_DOCS)


@pytest.mark.parametrize("slug", sorted(ALL_DOCS))
def test_every_page_has_a_title(slug: str) -> None:
    assert title_of(read_markdown(slug)) != ""


def test_keeps_all_the_typescript_apps_pages_each_marked_deprecated() -> None:
    deprecated = [*DEPRECATED_STEPS, *DEPRECATED_PAGES]
    assert len(DEPRECATED_STEPS) == 9
    assert len(DEPRECATED_PAGES) == 5
    assert all(doc.is_deprecated and doc.label.endswith("_deprecated") for doc in deprecated)
    assert not any(doc.is_deprecated for doc in CHAPTERS)


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("step-1.md", "/docs/step-1"),
        ("step-3_deprecated.md", "/docs_deprecated/step-3_deprecated"),
        ("issues.md", "/issues"),
        ("issues.md#step-1", "/issues#step-1"),
        ("technical-details_deprecated.md", "/technical-details_deprecated"),
        ("unknown.md", "unknown.md"),
        ("https://example.com/step-1.md", "https://example.com/step-1.md"),
        ("#top", "#top"),
        ("../README.md", "../README.md"),
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


def test_a_deprecated_pages_links_and_diagram_point_at_the_app() -> None:
    assert 'href="/docs_deprecated/step-3_deprecated"' in render_markdown(read_markdown("step-2_deprecated"))
    assert 'src="/docs/images/system-design_deprecated.png"' in render_markdown(
        read_markdown("system-design_deprecated")
    )
    assert (DOCS_IMAGES_DIR / "system-design_deprecated.png").is_file()


def test_finds_a_page_only_by_its_own_address() -> None:
    assert find_doc("/docs/step-1") == CHAPTERS[0]
    assert find_doc("/issues_deprecated") == DEPRECATED_PAGES[2]
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
