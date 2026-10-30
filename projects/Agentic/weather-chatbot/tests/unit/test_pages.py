"""
tests/unit/test_pages.py: the pages, through the app: each opens inside the shell, its menu link marked; the lists
name every page; a missing page gets the app's own 404 page, and a missing API, JSON.
"""

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.docs import CHAPTERS, DEPRECATED_PAGES, DEPRECATED_STEPS, DocPage, read_markdown, title_of
from nimbus.pages import DEPRECATED_MENU_ITEMS, MENU_ITEMS, to_aria_current, to_menu_label

DEPRECATED_NOTE = "Deprecated: this page describes the earlier TypeScript version of Nimbus."


def test_the_chat_page_shows_its_card_and_marks_its_menu_link(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "Nimbus (Weather)" in page.text
    assert '<a class="side-menu-link" href="/" aria-current="page">Chat</a>' in page.text
    assert "Build c7165ac · production" in page.text


def test_every_page_has_the_whole_menu(client: TestClient) -> None:
    page = client.get("/todo")
    for item in (*MENU_ITEMS, *DEPRECATED_MENU_ITEMS):
        assert f'href="{item.href}"' in page.text
        assert str(to_menu_label(item.label)) in page.text


def test_a_menu_label_may_break_before_deprecated_and_is_escaped() -> None:
    assert to_menu_label("Documentation_deprecated") == "Documentation<wbr>_deprecated"
    assert to_menu_label("Chat") == "Chat"
    assert to_menu_label("<b>_deprecated") == "&lt;b&gt;<wbr>_deprecated"


def test_the_documentation_lists_each_chapter(client: TestClient) -> None:
    page = client.get("/docs")
    assert page.status_code == 200
    for doc in CHAPTERS:
        assert f'<a href="{doc.path}">{escape(doc.label)}</a>' in page.text


def test_the_deprecated_documentation_lists_the_nine_steps_by_title(client: TestClient) -> None:
    page = client.get("/docs_deprecated")
    for doc in DEPRECATED_STEPS:
        assert f'<a href="{doc.path}">{escape(title_of(read_markdown(doc.slug)))}</a>' in page.text


@pytest.mark.parametrize("doc", [*CHAPTERS, *DEPRECATED_STEPS, *DEPRECATED_PAGES], ids=lambda doc: doc.slug)
def test_every_documentation_page_opens(client: TestClient, doc: DocPage) -> None:
    page = client.get(doc.path)
    assert page.status_code == 200
    assert f"<title>{escape(title_of(read_markdown(doc.slug)))} · Nimbus</title>" in page.text
    assert (DEPRECATED_NOTE in page.text) is doc.is_deprecated


@pytest.mark.parametrize("path", ["/issues", "/interview", "/todo"])
def test_the_pages_every_step_adds_to_open_and_mark_their_link(client: TestClient, path: str) -> None:
    page = client.get(path)
    assert page.status_code == 200
    assert f'href="{path}" aria-current="page"' in page.text


@pytest.mark.parametrize(
    ("path", "href", "expected"),
    [
        ("/", "/", "page"),
        ("/docs", "/", None),
        ("//docs", "/", None),
        ("/docs/step-1", "/docs", "true"),
        ("/docs_deprecated/step-1_deprecated", "/docs_deprecated", "true"),
        ("/docs_deprecated/step-1_deprecated", "/docs", None),
        ("/issues_deprecated", "/issues", None),
        ("/issues_deprecated", "/issues_deprecated", "page"),
    ],
)
def test_marks_a_menu_link_by_how_it_relates_to_the_address(path: str, href: str, expected: str | None) -> None:
    assert to_aria_current(path, href) == expected


@pytest.mark.parametrize(
    "path", ["/nowhere", "/docs/nowhere", "/docs/issues", "/docs_deprecated/step-1", "/x_deprecated"]
)
def test_a_missing_page_gets_the_apps_own_404_page(client: TestClient, path: str) -> None:
    page = client.get(path)
    assert page.status_code == 404
    assert "<h1>Page not found</h1>" in page.text
    assert 'aria-label="Main"' in page.text


def test_a_missing_api_gets_json(client: TestClient) -> None:
    answer = client.get("/api/nowhere")
    assert answer.status_code == 404
    assert answer.json() == {"detail": "Not Found"}


def test_fastapis_own_api_pages_are_off(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
    assert "swagger" not in client.get("/docs").text.lower()


def test_serves_the_stylesheet_and_the_docs_pictures(client: TestClient) -> None:
    assert client.get("/static/app.css").headers["content-type"].startswith("text/css")
    assert client.get("/docs/images/system-design_deprecated.png").headers["content-type"] == "image/png"


def test_on_vercel_leaves_the_stylesheet_to_the_cdn_and_still_serves_the_docs_pictures() -> None:
    with TestClient(create_app(Settings(_env_file=None, is_vercel=True))) as vercel_client:
        assert vercel_client.get("/static/app.css").status_code == 404
        assert vercel_client.get("/docs/images/system-design_deprecated.png").status_code == 200
