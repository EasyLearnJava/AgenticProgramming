"""
nimbus/pages.py: the app's pages: the chat (its shell, until step 2 makes it answer), the documentation, the system
design, the issues log, the interview guide and the to-do list, and the TypeScript app's pages, kept as *_deprecated.
Each is a Jinja2 template rendered on the server, inside the shell with the menu on the left (templates/base.html);
Jinja2 escapes every value put into a page but two marked safe: a doc's rendered Markdown and a menu label's <wbr>.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.exceptions import HTTPException as StarletteHTTPException

from nimbus.config import Settings
from nimbus.constants import TEMPLATES_DIR
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

HTTP_NOT_FOUND = 404
API_PREFIX = "/api/"


@dataclass(frozen=True)
class MenuItem:
    """A link in the left menu."""

    href: str
    label: str


@dataclass(frozen=True)
class ListEntry:
    """A line in a list of pages: its link, and a line about it."""

    href: str
    label: str
    summary: str = ""


# ① The menu: the chat, the documentation and the pages every step adds to, then the TypeScript app's pages, each
# renamed *_deprecated. Both lists come from the docs' registry, so a page can't be in one and not the other.
MENU_ITEMS: tuple[MenuItem, ...] = (
    MenuItem("/", "Chat"),
    MenuItem("/docs", "Documentation"),
    *(MenuItem(doc.path, doc.label) for doc in PAGES),
)
DEPRECATED_MENU_ITEMS: tuple[MenuItem, ...] = (
    MenuItem("/docs_deprecated", "Documentation_deprecated"),
    *(MenuItem(doc.path, doc.label) for doc in DEPRECATED_PAGES),
)


def to_aria_current(path: str, href: str) -> str | None:
    """How a menu link relates to the address: the page itself ("page"), a section it's in ("true"), or neither."""
    if path == href:
        return "page"
    if href != "/" and path.startswith(f"{href}/"):
        return "true"
    return None


def to_menu_label(label: str) -> Markup:
    """A menu label, escaped, that may break before "_deprecated": "Documentation_deprecated" is wider than the menu."""
    return escape(label).replace("_deprecated", Markup("<wbr>_deprecated"))


# ② The templates, with what every page's shell needs: the menu, how to mark its current link, and its labels.
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals.update(
    menu_items=MENU_ITEMS, deprecated_menu_items=DEPRECATED_MENU_ITEMS, to_aria_current=to_aria_current
)
templates.env.filters["menu_label"] = to_menu_label

router = APIRouter()


def _render(request: Request, template: str, context: Mapping[str, object], status_code: int = 200) -> HTMLResponse:
    """A page: its template, with the build's label for the menu's last line."""
    settings: Settings = request.app.state.settings
    return templates.TemplateResponse(
        request, template, {"build_label": settings.build_label, **context}, status_code=status_code
    )


def _render_doc(request: Request) -> HTMLResponse:
    """The documentation page at the request's address, from its Markdown; 404 for an address that isn't one."""
    doc = find_doc(request.url.path)
    if doc is None:
        raise HTTPException(status_code=HTTP_NOT_FOUND)
    markdown = read_markdown(doc.slug)
    context = {"title": title_of(markdown), "html": render_markdown(markdown), "is_deprecated": doc.is_deprecated}
    return _render(request, "doc.html", context)


# ③ The chat and the lists of pages.
@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    """The chat: its card and its welcome. From step 2, it answers."""
    return _render(request, "chat.html", {})


@router.get("/docs", response_class=HTMLResponse)
def docs_index(request: Request) -> HTMLResponse:
    """The documentation: a chapter for each step built so far."""
    entries = [ListEntry(doc.path, doc.label, doc.summary) for doc in CHAPTERS]
    intro = (
        "One chapter per step of the Python rebuild, written as the step is built: what it adds, the design, the code "
        "that matters, how to run and check it, the pitfalls, the issues we hit, and interview questions."
    )
    return _render(request, "docs_index.html", {"title": "Documentation", "intro": intro, "entries": entries})


@router.get("/docs_deprecated", response_class=HTMLResponse)
def deprecated_docs_index(request: Request) -> HTMLResponse:
    """The TypeScript app's step pages, kept as *_deprecated."""
    entries = [ListEntry(doc.path, title_of(read_markdown(doc.slug))) for doc in DEPRECATED_STEPS]
    intro = "The pages of Nimbus's first version, built in TypeScript in nine steps, kept for reference."
    context = {"title": "Documentation_deprecated", "intro": intro, "entries": entries}
    return _render(request, "docs_index.html", context)


# ④ The documentation pages, each found by its address: a chapter, the four pages every step adds to, and the
# TypeScript app's pages.
@router.get("/docs/{slug}", response_class=HTMLResponse)
def chapter_page(request: Request, slug: str) -> HTMLResponse:
    """A step's chapter."""
    return _render_doc(request)


@router.get("/system-design", response_class=HTMLResponse)
def system_design_page(request: Request) -> HTMLResponse:
    """The system design: how Nimbus is built so far, drawn the way a reference design for AI assistants is."""
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
    """The to-do list: what waits on the user, and what comes next."""
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
        return _render(request, "not_found.html", {}, status_code=HTTP_NOT_FOUND)
    return await http_exception_handler(request, error)
