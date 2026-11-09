"""
nimbus/pages.py: the app's pages: the chat (whose answers nimbus/chat.py streams), the documentation, the system
design, the issues log, the interview guide and the to-do list.
Each is a Jinja2 template rendered on the server, inside the shell with the menu on the left (templates/base.html),
its links in groups (step 14); the Observability pages are nimbus/observability.py's. Jinja2 escapes every value put
into a page except a doc's safely rendered Markdown.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from nimbus.chips import MARKS, WORDS
from nimbus.config import Settings
from nimbus.constants import (
    HISTORY_ANSWER_MAX_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_MAX_MESSAGES,
    QUESTION_MAX_CHARS,
    SOURCE_URL,
    TEMPLATES_DIR,
)
from nimbus.docs import (
    CHAPTERS,
    PAGES,
    find_doc,
    read_markdown,
    render_markdown,
    title_of,
)
from nimbus.errors import CUT_OFF, RATE_LIMITED, STOPPED, UNREACHABLE
from nimbus.feedback import CATEGORIES as FEEDBACK_CATEGORIES

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
    """A group of navigation links under one accessible heading."""

    title: str
    items: tuple[MenuItem, ...]

    @property
    def slug(self) -> str:
        """The heading's id in the page: its title in lower case."""
        return self.title.lower()


# ① Group navigation by purpose. The interview guide remains available by direct address.
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
            MenuItem("/weather-cache", "Weather cache"),
            MenuItem("/performance", "Performance"),
            MenuItem("/evaluations", "Evaluations"),
            MenuItem("/health", "Health"),
        ),
    ),
    MenuGroup(
        "Learn",
        (
            MenuItem("/docs", "Documentation"),
            *(DOC_ITEMS[slug] for slug in ("architecture", "system-design", "technical-details")),
        ),
    ),
    MenuGroup(
        "Project",
        (
            *(DOC_ITEMS[slug] for slug in ("issues", "todo", "waiting-on-you")),
            MenuItem(SOURCE_URL, "Source on GitHub", is_external=True),
            MenuItem("/api/health", "Health check (JSON)"),
            MenuItem("/health#mcp-server", "Weather MCP server"),
        ),
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
    """Whether a link in this group represents the current page or section."""
    return any(to_aria_current(path, item.href) is not None for item in group.items)


# ② The templates, with what every page's shell needs: the menu's groups, how to mark its current link, whether a
# group holds the page, and its labels.
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["feedback_categories"] = FEEDBACK_CATEGORIES
templates.env.globals.update(menu_groups=MENU_GROUPS, to_aria_current=to_aria_current, holds_page=holds_page)

router = APIRouter()


def render_page(request: Request, template: str, context: Mapping[str, object], status_code: int = 200) -> HTMLResponse:
    """A page: its template, with the build's label for the menu's last line."""
    settings: Settings = request.app.state.settings
    planner_enabled = settings.parks_enabled and (settings.flights_enabled or settings.hotels_enabled)
    menu = TRAVEL_MENU_GROUPS if planner_enabled else MENU_GROUPS
    if settings.memory_enabled:
        menu = (MenuGroup("App", (*menu[0].items, MenuItem("/preferences", "My preferences"))), *menu[1:])
    return templates.TemplateResponse(
        request,
        template,
        {
            "build_label": settings.build_label,
            "menu_groups": menu,
            "flights_enabled": settings.flights_enabled,
            "hotels_enabled": settings.hotels_enabled,
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
    context = {"title": title_of(markdown), "html": render_markdown(markdown)}
    return render_page(request, "doc.html", context)


# ③ The chat and the lists of pages.
@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    """Render the chat form and welcome message with the capabilities enabled on this deployment."""
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
    }
    return render_page(request, "chat.html", context)


@router.get("/docs", response_class=HTMLResponse)
def docs_index(request: Request) -> HTMLResponse:
    """The current reading guide and the chronological build chapters."""
    return render_page(request, "docs_index.html", {"title": "Documentation", "chapters": CHAPTERS})


# ④ Resolve published documentation by its registered address.
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


# ⑤ An error: a missing page gets our own 404 page; anything else, and a missing API, FastAPI's JSON.
async def http_error_response(request: Request, error: Exception) -> Response:
    """The response for an HTTP error raised anywhere in the app."""
    if not isinstance(error, StarletteHTTPException):
        raise error
    if error.status_code == HTTP_NOT_FOUND and not request.url.path.startswith(API_PREFIX):
        return render_page(request, "not_found.html", {}, status_code=HTTP_NOT_FOUND)
    return await http_exception_handler(request, error)
