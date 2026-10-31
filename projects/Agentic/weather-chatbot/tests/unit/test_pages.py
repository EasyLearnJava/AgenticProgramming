"""
tests/unit/test_pages.py: the pages, through the app: each opens inside the shell, its menu link marked; the chat's
form posts to the chat and loads only our own scripts, none inline; the lists name every page; a missing page gets the
app's own 404 page, and a missing API, JSON.
"""

import json
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.constants import QUESTION_MAX_CHARS
from nimbus.docs import CHAPTERS, DEPRECATED_PAGES, DEPRECATED_STEPS, PAGES, DocPage, read_markdown, title_of
from nimbus.errors import CUT_OFF, STOPPED, UNREACHABLE
from nimbus.pages import DEPRECATED_MENU_ITEMS, MENU_ITEMS, to_aria_current, to_menu_label

DEPRECATED_NOTE = "Deprecated: this page describes the earlier TypeScript version of Nimbus."


def test_the_chat_page_shows_its_card_and_marks_its_menu_link(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "Nimbus (Weather)" in page.text
    assert '<a class="side-menu-link" href="/" aria-current="page">Chat</a>' in page.text
    assert "Build c7165ac · production" in page.text


class _Elements(HTMLParser):
    """A page's elements, read as a browser would: their attributes by id, the scripts it loads, its meta tags."""

    def __init__(self, page: str) -> None:
        """Reads the page."""
        super().__init__()
        self.by_id: dict[str, dict[str, str | None]] = {}
        self.scripts: list[str | None] = []
        self.metas: dict[str, str | None] = {}
        self.attribute_names: set[str] = set()
        self.feed(page)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Keeps what the tests look at."""
        attributes = dict(attrs)
        self.attribute_names |= set(attributes)
        if attributes.get("id"):
            self.by_id[str(attributes["id"])] = attributes
        if tag == "script":
            self.scripts.append(attributes.get("src"))
        if tag == "meta" and attributes.get("name"):
            self.metas[str(attributes["name"])] = attributes.get("content")


def test_the_chat_form_posts_each_question_and_adds_its_streamed_answer_to_the_conversation(
    client: TestClient,
) -> None:
    page = _Elements(client.get("/").text)
    form = page.by_id["chat-form"]
    # Without htmx, the browser posts the form itself: a question never goes into the address.
    assert form["method"] == "post"
    assert form["action"] == "/api/chat"
    assert form["hx-post"] == "/api/chat"
    assert form["hx-target"] == "#messages"
    assert form["hx-swap"] == "beforeend"
    assert form["hx-sync"] == "this:drop"
    question = page.by_id["question"]
    assert question["name"] == "question"
    assert question["maxlength"] == str(QUESTION_MAX_CHARS)
    assert "required" in question
    assert "disabled" not in question
    assert page.by_id["send"]["type"] == "submit"
    assert page.by_id["stop"]["type"] == "button"


def test_the_chat_page_loads_htmx_its_stream_extension_and_our_script_and_nothing_inline(client: TestClient) -> None:
    page = _Elements(client.get("/").text)
    assert page.scripts == ["/static/htmx.min.js", "/static/hx-sse.min.js", "/static/chat.js"]
    assert not [name for name in page.attribute_names if name.startswith(("on", "hx-on"))]
    content = page.metas["htmx-config"]
    assert content is not None
    assert json.loads(content) == {"extensions": "sse", "includeIndicatorCSS": False, "history": False}


def test_the_chat_page_holds_the_sentences_our_script_shows(client: TestClient) -> None:
    page = _Elements(client.get("/").text)
    messages = page.by_id["messages"]
    assert messages["data-stopped"] == STOPPED
    assert messages["data-cut-off"] == CUT_OFF
    assert messages["data-unreachable"] == UNREACHABLE
    assert messages["aria-live"] == "polite"
    assert "chat-error-template" in page.by_id


def test_only_the_chat_page_loads_scripts(client: TestClient) -> None:
    assert "<script" not in client.get("/docs").text
    assert "<script" not in client.get("/docs/step-1").text


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


@pytest.mark.parametrize("doc", PAGES, ids=lambda doc: doc.slug)
def test_the_pages_every_step_adds_to_open_and_mark_their_link(client: TestClient, doc: DocPage) -> None:
    page = client.get(doc.path)
    assert page.status_code == 200
    assert f'href="{doc.path}" aria-current="page"' in page.text


def test_the_menu_lists_the_chat_the_documentation_then_the_pages_every_step_adds_to() -> None:
    assert [item.href for item in MENU_ITEMS] == ["/", "/docs", "/system-design", "/issues", "/interview", "/todo"]


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
