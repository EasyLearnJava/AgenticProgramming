"""
nimbus/pages.py: the app's pages: the chat (whose answers nimbus/chat.py streams), the documentation, the system
design, the issues log, the interview guide and the to-do list, and the TypeScript app's pages, kept as *_deprecated.
Each is a Jinja2 template rendered on the server, inside the shell with the menu on the left (templates/base.html),
its links in groups (step 14); the Observability pages are nimbus/observability.py's. Jinja2 escapes every value put
into a page but two marked safe: a doc's rendered Markdown and a menu label's <wbr>.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.exceptions import HTTPException as StarletteHTTPException

from nimbus.actor import to_actor_input
from nimbus.apify import to_call_actor_example, to_rest_request
from nimbus.chips import MARKS, WORDS
from nimbus.config import Settings
from nimbus.constants import (
    HISTORY_ANSWER_MAX_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_MAX_MESSAGES,
    MCP_PATH,
    QUESTION_MAX_CHARS,
    SOURCE_URL,
    TEMPLATES_DIR,
)
from nimbus.docs import (
    CHAPTERS,
    DEPRECATED_PAGES,
    DEPRECATED_STEPS,
    PAGES,
    find_doc,
    read_markdown,
    render_markdown,
    title_of,
)
from nimbus.errors import CUT_OFF, RATE_LIMITED, STOPPED, UNREACHABLE
from nimbus.lanes import LANES, MCP_NO_AUTH, MCP_WITH_AUTH, REST_NO_AUTH, REST_WITH_AUTH, Lane, is_open
from nimbus.mcp_lane import to_tools_call
from nimbus.open_meteo import to_forecast_request
from nimbus.tools import ForecastInput

HTTP_NOT_FOUND = 404
API_PREFIX = "/api/"


@dataclass(frozen=True)
class MenuItem:
    """A link in the left menu: where it goes, its words, and whether it leaves the site (step 14)."""

    href: str
    label: str
    is_external: bool = False


@dataclass(frozen=True)
class MenuGroup:
    """A group of the menu's links, under its heading; a folded one stays shut unless its links hold the page."""

    title: str
    items: tuple[MenuItem, ...]
    is_folded: bool = False

    @property
    def slug(self) -> str:
        """The heading's id in the page: its title in lower case."""
        return self.title.lower()


@dataclass(frozen=True)
class ListEntry:
    """A line in a list of pages: its link, and a line about it."""

    href: str
    label: str
    summary: str = ""


# ① The menu, in groups (step 14): the chat; the Observability pages; the pages to learn from; the project's own;
# links for a developer; and the TypeScript app's pages, each renamed *_deprecated, folded. The pages every step adds
# to come from the docs' registry, by their slugs; a test checks each is in one group.
DOC_ITEMS: dict[str, MenuItem] = {doc.slug: MenuItem(doc.path, doc.label) for doc in PAGES}
MENU_GROUPS: tuple[MenuGroup, ...] = (
    MenuGroup("App", (MenuItem("/", "Chat"), MenuItem("/parks/alerts", "Park alerts"))),
    MenuGroup(
        "Knowledge",
        (
            MenuItem("/knowledge/sources", "Source documents"),
            MenuItem("/knowledge/chunks", "Chunks & vectors"),
            MenuItem("/knowledge/retrieval", "Retrieval Playground"),
        ),
    ),
    MenuGroup(
        "Observability",
        (
            MenuItem("/activity", "Activity"),
            MenuItem("/performance", "Performance"),
            MenuItem("/evaluations", "Evaluations"),
            MenuItem("/health", "Health"),
        ),
    ),
    MenuGroup(
        "Learn",
        (
            MenuItem("/docs", "Documentation"),
            *(DOC_ITEMS[slug] for slug in ("architecture", "system-design", "technical-details", "interview")),
        ),
    ),
    MenuGroup("Project", tuple(DOC_ITEMS[slug] for slug in ("issues", "todo", "waiting-on-you"))),
    MenuGroup(
        "Links",
        (
            MenuItem(SOURCE_URL, "Source on GitHub", is_external=True),
            MenuItem("/api/health", "Health check (JSON)"),
            MenuItem("/health#mcp-server", "MCP server"),
        ),
    ),
    MenuGroup(
        "Deprecated",
        (
            MenuItem("/docs_deprecated", "Documentation_deprecated"),
            *(MenuItem(doc.path, doc.label) for doc in DEPRECATED_PAGES),
        ),
        is_folded=True,
    ),
)


# Select the navigation for this deployment without mutating the shared base menu.
TRAVEL_MENU_GROUPS = (
    MenuGroup("App", (*MENU_GROUPS[0].items, MenuItem("/parks/trip", "Plan a park trip"))),
    *MENU_GROUPS[1:],
)


def to_aria_current(path: str, href: str) -> str | None:
    """How a menu link relates to the address: the page itself ("page"), a section it's in ("true"), or neither."""
    if path == href:
        return "page"
    if href != "/" and path.startswith(f"{href}/"):
        return "true"
    return None


def holds_page(group: MenuGroup, path: str) -> bool:
    """Whether one of the group's links is the page at the address, or a section it's in: a folded group opens then."""
    return any(to_aria_current(path, item.href) is not None for item in group.items)


def to_menu_label(label: str) -> Markup:
    """A menu label, escaped, that may break before "_deprecated": "Documentation_deprecated" is wider than the menu."""
    return escape(label).replace("_deprecated", Markup("<wbr>_deprecated"))


# ② The templates, with what every page's shell needs: the menu's groups, how to mark its current link, whether a
# group holds the page, and its labels.
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals.update(menu_groups=MENU_GROUPS, to_aria_current=to_aria_current, holds_page=holds_page)
templates.env.filters["menu_label"] = to_menu_label

router = APIRouter()


def render_page(request: Request, template: str, context: Mapping[str, object], status_code: int = 200) -> HTMLResponse:
    """A page: its template, with the build's label for the menu's last line."""
    settings: Settings = request.app.state.settings
    planner_enabled = settings.parks_enabled and (settings.flights_enabled or settings.hotels_enabled)
    return templates.TemplateResponse(
        request,
        template,
        {
            "build_label": settings.build_label,
            "menu_groups": TRAVEL_MENU_GROUPS if planner_enabled else MENU_GROUPS,
            **context,
        },
        status_code=status_code,
    )


def _render_doc(request: Request) -> HTMLResponse:
    """The documentation page at the request's address, from its Markdown; 404 for an address that isn't one."""
    doc = find_doc(request.url.path)
    if doc is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND)
    markdown = read_markdown(doc.slug)
    context = {"title": title_of(markdown), "html": render_markdown(markdown), "is_deprecated": doc.is_deprecated}
    return render_page(request, "doc.html", context)


# ③ The chat and the lists of pages.
@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    """
    The chat: its card, its welcome and its form, with the sentences the page shows by itself (chat.js), a chip's mark
    and word when Stop ends its call, and the limits of the conversation it sends back; and the lane picker and the
    compare view (step 9).
    """
    context = {
        "question_max_chars": QUESTION_MAX_CHARS,
        "stopped": STOPPED,
        "cut_off": CUT_OFF,
        "unreachable": UNREACHABLE,
        "rate_limited": RATE_LIMITED,
        "chip_stopped_mark": MARKS["stopped"],
        "chip_stopped_word": f"{WORDS['stopped']}:",
        "history_max_messages": HISTORY_MAX_MESSAGES,
        "history_max_chars": HISTORY_MAX_CHARS,
        "answer_max_chars": HISTORY_ANSWER_MAX_CHARS,
        "lanes": [(lane, is_open(lane, request.app.state.settings)) for lane in LANES],
        "default_lane": REST_NO_AUTH.id,
        "compare": to_compare_cells(request),
    }
    return render_page(request, "chat.html", context)


@dataclass(frozen=True)
class CompareCell:
    """One lane in the compare view (step 9): the lane, the request its forecast call sends, if it's open, a note."""

    lane: Lane
    request: str | None
    note: str


# The compare view's call: Paris's forecast, 2 days, in metric units, as the model would ask for it.
COMPARE_CALL = ForecastInput(latitude=48.85, longitude=2.35, days=2, include_hourly=False, units="metric")
COMPARE_NOTES = {
    REST_NO_AUTH.id: "One request: from the chat's own function to Open-Meteo.",
    MCP_NO_AUTH.id: (
        "A JSON-RPC message to our own MCP server, which then sends Open-Meteo the request beside it. The SDK's "
        "client adds its own headers and the protocol's _meta: a chip shows them as they're sent."
    ),
    REST_WITH_AUTH.id: (
        "One request: Apify runs the Actor, which asks Open-Meteo, and answers with its items. The token goes in a "
        "header, masked here; if the run fails, REST · no auth answers."
    ),
    MCP_WITH_AUTH.id: (
        "After the 2025 handshake, call-actor runs the Actor with the same three limits, then get-dataset-items reads "
        "its items. The token is masked here; if the run fails, MCP · no auth answers."
    ),
}


def to_compare_cells(request: Request) -> list[CompareCell]:
    """The compare view: the same forecast call through each lane, each open lane's request made by its own code."""
    state = request.app.state
    arguments = COMPARE_CALL.model_dump(mode="json")
    mcp_url = state.to_mcp_url(request, state.settings) or MCP_PATH
    actor_input = to_actor_input(COMPARE_CALL)
    requests = {
        REST_NO_AUTH.id: to_forecast_request(**arguments).to_text(),
        MCP_NO_AUTH.id: to_tools_call(mcp_url, "get_forecast", arguments).to_text(),
        REST_WITH_AUTH.id: to_rest_request(actor_input).to_text(),
        MCP_WITH_AUTH.id: to_call_actor_example(actor_input).to_text(),
    }
    return [
        CompareCell(lane, requests.get(lane.id), COMPARE_NOTES.get(lane.id, f"Opens in step {lane.step}."))
        for lane in LANES
    ]


@router.get("/docs", response_class=HTMLResponse)
def docs_index(request: Request) -> HTMLResponse:
    """The documentation: a chapter for each step built so far."""
    entries = [ListEntry(doc.path, doc.label, doc.summary) for doc in CHAPTERS]
    intro = (
        "One chapter per step of the Python rebuild, written as the step is built: what it adds, the design, the code "
        "that matters, how to run and check it, the pitfalls, the issues we hit, and interview questions."
    )
    return render_page(request, "docs_index.html", {"title": "Documentation", "intro": intro, "entries": entries})


@router.get("/docs_deprecated", response_class=HTMLResponse)
def deprecated_docs_index(request: Request) -> HTMLResponse:
    """The TypeScript app's step pages, kept as *_deprecated."""
    entries = [ListEntry(doc.path, title_of(read_markdown(doc.slug))) for doc in DEPRECATED_STEPS]
    intro = "The pages of Nimbus's first version, built in TypeScript in nine steps, kept for reference."
    context = {"title": "Documentation_deprecated", "intro": intro, "entries": entries}
    return render_page(request, "docs_index.html", context)


# ④ The documentation pages, each found by its address: a chapter, the four pages every step adds to, and the
# TypeScript app's pages.
@router.get("/docs/{slug}", response_class=HTMLResponse)
def chapter_page(request: Request, slug: str) -> HTMLResponse:
    """A step's chapter."""
    return _render_doc(request)


@router.get("/architecture", response_class=HTMLResponse)
def architecture_page(request: Request) -> HTMLResponse:
    """The whole design on one page: features, architecture, data flow, decisions, safety and security."""
    return _render_doc(request)


@router.get("/system-design", response_class=HTMLResponse)
def system_design_page(request: Request) -> HTMLResponse:
    """The system design: how Nimbus is built so far, drawn the way a reference design for AI assistants is."""
    return _render_doc(request)


@router.get("/technical-details", response_class=HTMLResponse)
def technical_details_page(request: Request) -> HTMLResponse:
    """One question, followed through the code, with the lines it left (step 13)."""
    return _render_doc(request)


@router.get("/issues", response_class=HTMLResponse)
def issues_page(request: Request) -> HTMLResponse:
    """The issues log: every problem met while building, how it was found, and how it was fixed."""
    return _render_doc(request)


@router.get("/interview", response_class=HTMLResponse)
def interview_page(request: Request) -> HTMLResponse:
    """The interview guide: each step's questions, with short answers."""
    return _render_doc(request)


@router.get("/todo", response_class=HTMLResponse)
def todo_page(request: Request) -> HTMLResponse:
    """The to-do list: what's done, and what comes next."""
    return _render_doc(request)


@router.get("/waiting-on-you", response_class=HTMLResponse)
def waiting_on_you_page(request: Request) -> HTMLResponse:
    """Everything only the user can do, in their own accounts, step by step (step 12)."""
    return _render_doc(request)


@router.get("/docs_deprecated/{slug}", response_class=HTMLResponse)
def deprecated_step_page(request: Request, slug: str) -> HTMLResponse:
    """One of the TypeScript app's step pages."""
    return _render_doc(request)


@router.get("/{name}_deprecated", response_class=HTMLResponse)
def deprecated_page(request: Request, name: str) -> HTMLResponse:
    """One of the TypeScript app's other pages: its system design, technical details, issues log and the rest."""
    return _render_doc(request)


# ⑤ An error: a missing page gets our own 404 page; anything else, and a missing API, FastAPI's JSON.
async def http_error_response(request: Request, error: Exception) -> Response:
    """The response for an HTTP error raised anywhere in the app."""
    if not isinstance(error, StarletteHTTPException):
        raise error
    if error.status_code == HTTP_NOT_FOUND and not request.url.path.startswith(API_PREFIX):
        return render_page(request, "not_found.html", {}, status_code=HTTP_NOT_FOUND)
    return await http_exception_handler(request, error)
