"""
nimbus/docs.py: the documentation: a chapter for each step, the issues log, the interview guide and the to-do list,
and the TypeScript app's pages, kept as *_deprecated. Each page is a Markdown file in docs/, written to read the same
on GitHub; here it becomes HTML, with raw HTML never rendered, and with its GitHub-style links (step-2.md) and
pictures (images/x.png) turned into the app's own addresses.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

from nimbus.constants import DOCS_DIR

DOC_LINK = re.compile(r"(?P<slug>[\w-]+)\.md(?P<fragment>#[\w-]*)?", re.ASCII)
IMAGES_PREFIX = "images/"
DEPRECATED_STEP_COUNT = 9


@dataclass(frozen=True)
class DocPage:
    """One page: its file's name without .md, its address in the app, how lists name it, and a line about it."""

    slug: str
    path: str
    label: str
    summary: str = ""
    is_deprecated: bool = False


# ① The new app's pages: a chapter for each step, and the four pages every step adds to.
CHAPTERS: tuple[DocPage, ...] = (
    DocPage(
        slug="step-1",
        path="/docs/step-1",
        label="Step 1: The Project, Its Pages and Its First Deploy",
        summary=(
            "A FastAPI app with uv, Ruff, mypy and pytest; the pages in Jinja2, with Nimbus's look; the docs rendered "
            "from Markdown; a request id on every log line; the security headers; CI; and the first deploy to Vercel."
        ),
    ),
    DocPage(
        slug="step-2",
        path="/docs/step-2",
        label="Step 2: The Chat Streams Its Answer",
        summary=(
            "POST /api/chat streams a fixed answer as server-sent events of HTML, which htmx 4 puts into the page a "
            "word at a time; Stop ends it, on the page and on the server; and our own sentence for each thing that "
            "can go wrong."
        ),
    ),
    DocPage(
        slug="step-3",
        path="/docs/step-3",
        label="Step 3: Gemini Answers, Streamed",
        summary=(
            "Gemini, through LangChain, streams the answer: a system prompt with the visitor's locale and time zone, "
            "caps on each answer's tokens and time, our own sentence for each way the model can fail, the answer's "
            "Markdown made safe HTML, and LangSmith tracing only with inputs and outputs hidden."
        ),
    ),
    DocPage(
        slug="step-4",
        path="/docs/step-4",
        label="Step 4: The Weather Tools, and an Agent That Calls Them",
        summary=(
            "Four weather tools call Open-Meteo from the chat's own function, the REST · no auth lane; LangChain's "
            "prebuilt agent runs them for Gemini; each call shows as a chip that opens to its request; the model reads "
            "the weather only, and answers by the TypeScript version's 13 rules."
        ),
    ),
)
PAGES: tuple[DocPage, ...] = (
    DocPage(slug="system-design", path="/system-design", label="System design"),
    DocPage(slug="issues", path="/issues", label="Issues and fixes"),
    DocPage(slug="interview", path="/interview", label="Interview guide"),
    DocPage(slug="todo", path="/todo", label="To do"),
)

# ② The TypeScript app's pages, kept until the user says otherwise, each renamed *_deprecated, at its old address with
# the same suffix: /docs/step-3 is now /docs_deprecated/step-3_deprecated, /issues is /issues_deprecated.
DEPRECATED_STEPS: tuple[DocPage, ...] = tuple(
    DocPage(
        slug=f"step-{n}_deprecated",
        path=f"/docs_deprecated/step-{n}_deprecated",
        label=f"Step {n}_deprecated",
        is_deprecated=True,
    )
    for n in range(1, DEPRECATED_STEP_COUNT + 1)
)
DEPRECATED_PAGES: tuple[DocPage, ...] = tuple(
    DocPage(slug=f"{name}_deprecated", path=f"/{name}_deprecated", label=f"{label}_deprecated", is_deprecated=True)
    for name, label in (
        ("system-design", "System design"),
        ("technical-details", "Technical details"),
        ("issues", "Issues and fixes"),
        ("interview", "Interview guide"),
        ("todo", "To do"),
    )
)
ALL_DOCS: dict[str, DocPage] = {doc.slug: doc for doc in (*CHAPTERS, *PAGES, *DEPRECATED_STEPS, *DEPRECATED_PAGES)}
DOC_BY_PATH: dict[str, DocPage] = {doc.path: doc for doc in ALL_DOCS.values()}


def to_app_url(href: str) -> str:
    """
    A link written for GitHub, "step-2.md" or "issues.md#step-1", as the app's own address: "/docs/step-2",
    "/issues#step-1". Any other link stays as it is.
    """
    match = DOC_LINK.fullmatch(href)
    doc = None if match is None else ALL_DOCS.get(match["slug"])
    if match is None or doc is None:
        return href
    return doc.path + (match["fragment"] or "")


def to_image_url(src: str) -> str:
    """A picture beside the docs, "images/x.png", at the address the app serves it from: "/docs/images/x.png"."""
    return f"/docs/{src}" if src.startswith(IMAGES_PREFIX) else src


def _link_open(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    """Renders a link's opening tag, its address turned into the app's own (to_app_url)."""
    href = tokens[idx].attrGet("href")
    if isinstance(href, str):
        tokens[idx].attrSet("href", to_app_url(href))
    return renderer.renderToken(tokens, idx, options, env)


def _image(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    """Renders a picture, from the address the app serves it at (to_image_url)."""
    src = tokens[idx].attrGet("src")
    if isinstance(src, str):
        tokens[idx].attrSet("src", to_image_url(src))
    return renderer.image(tokens, idx, options, env)


def _cell_open(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    """
    Renders a table cell's opening tag, its alignment as a class (align-right): markdown-it writes it as an inline
    style, which the Content Security Policy refuses.
    """
    style = tokens[idx].attrGet("style")
    if isinstance(style, str):
        del tokens[idx].attrs["style"]
        tokens[idx].attrSet("class", f"align-{style.removeprefix('text-align:')}")
    return renderer.renderToken(tokens, idx, options, env)


def _create_markdown() -> MarkdownIt:
    """CommonMark with GitHub's tables and strikethrough; raw HTML off, so a page can only ever be text and links."""
    markdown = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    markdown.add_render_rule("link_open", _link_open)
    markdown.add_render_rule("image", _image)
    markdown.add_render_rule("th_open", _cell_open)
    markdown.add_render_rule("td_open", _cell_open)
    return markdown


MARKDOWN = _create_markdown()


def find_doc(path: str) -> DocPage | None:
    """The page at an address; None for any other: an address never becomes a file path by itself."""
    return DOC_BY_PATH.get(path)


@cache
def read_markdown(slug: str) -> str:
    """A page's Markdown, read once: the files don't change while a deployment runs."""
    return (DOCS_DIR / f"{ALL_DOCS[slug].slug}.md").read_text(encoding="utf-8")


def render_markdown(markdown: str) -> Markup:
    """A page's HTML. Safe to put in a template as it is: with raw HTML off, every tag in it is markdown-it's own."""
    return Markup(MARKDOWN.render(markdown))  # noqa: S704


def title_of(markdown: str) -> str:
    """A page's title: its first heading's text ("# Step 1 · The Shell" → "Step 1 · The Shell")."""
    return next((line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")), "")
