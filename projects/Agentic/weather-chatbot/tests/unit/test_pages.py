"""
tests/unit/test_pages.py: the pages, through the app: each opens inside the shell, its menu link marked; the menu in
its groups (step 14), a link that leaves the site saying so; the
chat's form posts to the chat and loads only our own scripts, none inline; the lists name every page; a missing page
gets the app's own 404 page, and a missing API, JSON.
"""

import json
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape
from pydantic import SecretStr

from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.constants import QUESTION_MAX_CHARS, SOURCE_URL
from nimbus.docs import CHAPTERS, PAGES, DocPage, read_markdown, title_of
from nimbus.errors import CUT_OFF, RATE_LIMITED, STOPPED, UNREACHABLE
from nimbus.pages import MENU_GROUPS, to_aria_current


def test_the_chat_page_shows_its_card_and_marks_its_menu_link(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert 'class="chat-title">Nimbus</h1>' in page.text
    assert '<a class="side-menu-link" href="/" aria-current="page">Chat</a>' in page.text
    assert "Build c7165ac · production" in page.text


@pytest.mark.parametrize(
    ("parks", "flights", "hotels"),
    [(True, True, True), (True, True, False), (True, False, False), (False, False, True), (False, False, False)],
)
def test_the_chat_introduction_describes_enabled_capabilities(
    settings: Settings, parks: bool, flights: bool, hotels: bool
) -> None:
    """Look only inside the chat card, excluding the shared documentation and navigation labels."""
    settings = settings.model_copy(
        update={"parks_enabled": parks, "flights_enabled": flights, "hotels_enabled": hotels}
    )
    with TestClient(create_app(settings)) as client:
        card = client.get("/").text.split('id="chat-title"', 1)[1].split('id="chat-error-template"', 1)[0].lower()
    assert "forecasts" in card
    assert "air quality" in card
    assert ("park alerts" in card) is parks
    assert ("plan a trip" in card) is (parks and (flights or hotels))
    assert ("flights" in card) is flights
    assert ("hotels" in card) is hotels


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
    assert page.scripts == [
        "/static/htmx.min.js",
        "/static/hx-sse.min.js",
        "/static/chat.js",
        "/static/chat-planner.js",
    ]
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
    assert messages["data-rate-limited"] == RATE_LIMITED
    assert messages["aria-live"] == "polite"
    assert "chat-error-template" in page.by_id


def test_the_chat_page_says_where_questions_go(client: TestClient) -> None:
    # Step 11: on Gemini's free tier, Google may use what it gets; the page says so, under the form.
    note = "Your questions go to Google's Gemini, which may use them to improve its products: share nothing personal."
    assert note in client.get("/").text


def test_only_the_chat_page_loads_scripts(client: TestClient) -> None:
    assert "<script" not in client.get("/docs").text
    assert "<script" not in client.get("/docs/step-1").text


def test_every_page_has_the_whole_menu_each_group_under_its_heading(client: TestClient) -> None:
    page = client.get("/todo")
    for group in MENU_GROUPS:
        assert f'id="menu-{group.slug}">{group.title}<' in page.text
        assert f'<ul class="side-menu-items" aria-labelledby="menu-{group.slug}">' in page.text
        for item in group.items:
            assert f'href="{escape(item.href)}"' in page.text
            assert escape(item.label) in page.text


def test_navigation_omits_retired_links(client: TestClient) -> None:
    html = client.get("/").text
    nav = html.split('<nav class="side-menu"', 1)[1].split("</nav>", 1)[0]
    assert "deprecated" not in nav.lower()


def test_a_link_that_leaves_the_site_says_so(client: TestClient) -> None:
    page = client.get("/")
    link = f'<a class="side-menu-link" href="{SOURCE_URL}" rel="external noopener">Source on GitHub'
    assert link in page.text
    assert '<span class="visually-hidden"> (leaves this site)</span></a>' in page.text
    assert [item.href for group in MENU_GROUPS for item in group.items if item.is_external] == [SOURCE_URL]


def test_the_documentation_lists_each_chapter(client: TestClient) -> None:
    page = client.get("/docs")
    assert page.status_code == 200
    main = page.text.split('<main class="doc">', 1)[1].split("</main>", 1)[0]
    for href in ("/architecture", "/system-design", "/technical-details", "/knowledge/retrieval", "/evaluations"):
        assert f'href="{href}"' in main
    assert 'href="/interview"' not in page.text
    for doc in CHAPTERS:
        assert f'<a href="{doc.path}">{escape(doc.label)}</a>' in main


@pytest.mark.parametrize("doc", CHAPTERS, ids=lambda doc: doc.slug)
def test_every_documentation_page_opens(client: TestClient, doc: DocPage) -> None:
    page = client.get(doc.path)
    assert page.status_code == 200
    assert f"<title>{escape(title_of(read_markdown(doc.slug)))} · Nimbus</title>" in page.text


@pytest.mark.parametrize("doc", [doc for doc in PAGES if doc.slug != "interview"], ids=lambda doc: doc.slug)
def test_the_pages_every_step_adds_to_open_and_mark_their_link(client: TestClient, doc: DocPage) -> None:
    page = client.get(doc.path)
    assert page.status_code == 200
    assert f'href="{doc.path}" aria-current="page"' in page.text


def test_the_interview_guide_is_readable_from_a_bookmark_and_hidden_from_navigation(client: TestClient) -> None:
    page = client.get("/interview")
    assert page.status_code == 200
    assert f"<h1>{escape(title_of(read_markdown('interview')))}</h1>" in page.text
    assert 'href="/interview"' not in page.text


def test_the_menu_lists_its_groups_each_with_its_links() -> None:
    assert [(group.title, [item.href for item in group.items]) for group in MENU_GROUPS] == [
        ("App", ["/", "/parks/alerts"]),
        ("Knowledge", ["/knowledge/sources", "/knowledge/chunks", "/knowledge/retrieval"]),
        ("Observability", ["/activity", "/weather-cache", "/performance", "/evaluations", "/health"]),
        ("Learn", ["/docs", "/architecture", "/system-design", "/technical-details"]),
        ("Project", ["/issues", "/todo", "/waiting-on-you", SOURCE_URL, "/api/health", "/health#mcp-server"]),
    ]


def test_each_visible_document_belongs_to_one_menu_group() -> None:
    for doc in PAGES:
        groups = [group for group in MENU_GROUPS if any(item.href == doc.path for item in group.items)]
        assert len(groups) == (0 if doc.slug == "interview" else 1), doc.slug


@pytest.mark.parametrize("href", [item.href for group in MENU_GROUPS for item in group.items if not item.is_external])
def test_no_link_in_the_menu_is_broken(client: TestClient, href: str) -> None:
    assert client.get(href.partition("#")[0]).status_code != 404


@pytest.mark.parametrize(
    ("path", "href", "expected"),
    [
        ("/", "/", "page"),
        ("/docs", "/", None),
        ("//docs", "/", None),
        ("/docs/step-1", "/docs", "true"),
        ("/documentation", "/docs", None),
    ],
)
def test_marks_a_menu_link_by_how_it_relates_to_the_address(path: str, href: str, expected: str | None) -> None:
    assert to_aria_current(path, href) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/nowhere",
        "/docs/nowhere",
        "/docs/issues",
        "/docs_deprecated",
        "/docs/images/system-design_deprecated.png",
        *(f"/docs_deprecated/step-{n}_deprecated" for n in range(1, 10)),
        *(f"/{name}_deprecated" for name in ("system-design", "technical-details", "issues", "interview", "todo")),
    ],
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
    assert client.get("/docs/images/system-design.svg").headers["content-type"] == "image/svg+xml"


def test_on_vercel_leaves_the_stylesheet_to_the_cdn_and_still_serves_the_docs_pictures() -> None:
    with TestClient(create_app(Settings(_env_file=None, is_vercel=True))) as vercel_client:
        assert vercel_client.get("/static/app.css").status_code == 404
        assert vercel_client.get("/docs/images/system-design.svg").status_code == 200


@pytest.mark.parametrize("token", [None, SecretStr("test-apify-token")], ids=["no-token", "token"])
def test_the_chat_page_uses_the_server_default_without_showing_lane_controls(
    settings: Settings, token: SecretStr | None
) -> None:
    """Both deployment configurations serve the same composer and leave lane selection to the API default."""
    app = create_app(settings.model_copy(update={"apify_token": token}))
    with TestClient(app) as client:
        page = client.get("/").text
    assert 'name="lane"' not in page
    assert "Compare the lanes" not in page
    assert "Lane: how the tools are reached" not in page
    assert "data-lane-status" not in page
    assert "test-apify-token" not in page
