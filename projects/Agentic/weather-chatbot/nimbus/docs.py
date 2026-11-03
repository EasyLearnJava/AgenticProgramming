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
    DocPage(
        slug="step-5",
        path="/docs/step-5",
        label="Step 5: The Agent as a Graph of Our Own",
        summary=(
            "A LangGraph graph of our own in place of the prebuilt agent: its last call to the model with the tools "
            "turned off, so every answer ends in words; each tool call a task of its own; and time limits on each "
            "call's first words and on each tool call."
        ),
    ),
    DocPage(
        slug="step-6",
        path="/docs/step-6",
        label="Step 6: The Chat Remembers, in the Browser",
        summary=(
            "The page keeps the conversation and sends it back with each question, as untrusted input: questions and "
            "answers in turn, checked and capped, never a tool's result, so the tools run again; and New chat."
        ),
    ),
    DocPage(
        slug="step-7",
        path="/docs/step-7",
        label="Step 7: Open-Meteo's Answers, Cached",
        summary=(
            "Open-Meteo's answers kept in Vercel's Runtime Cache, under our namespace, each key a SHA-256 and each "
            "kind for its own time; a cache that fails or is slow is a miss; and the chip says when it answered."
        ),
    ),
    DocPage(
        slug="step-8",
        path="/docs/step-8",
        label="Step 8: Our Own MCP Server",
        summary=(
            "The four weather tools offered to any MCP client at /api/mcp, from the same definitions the agent runs "
            "over REST: the official SDK's MCPServer, with no session and JSON answers; and a client to call it."
        ),
    ),
    DocPage(
        slug="step-9",
        path="/docs/step-9",
        label="Step 9: The MCP · No Auth Lane",
        summary=(
            "A lane picker, and the agent's tools reached through our own MCP server on this same deployment, at an "
            "address of its own; the chips show both hops, and a compare view one forecast call through each lane."
        ),
    ),
    DocPage(
        slug="step-10",
        path="/docs/step-10",
        label="Step 10: The Lanes With Auth, Through Apify",
        summary=(
            "The forecast through Apify's Actor, over its REST API or its MCP server, behind a token, pinned and "
            "capped; the other tools, and any failure, by the twin with no auth, the chip saying why."
        ),
    ),
    DocPage(
        slug="step-11",
        path="/docs/step-11",
        label="Step 11: Security: Rate Limits, Prompt Injection, Privacy",
        summary=(
            "Vercel's firewall, a bypass for the app's own calls then a rate limit, its 429 in our words; a rule "
            "against prompt injection; and privacy checks, tests of what never leaves the app, on every lane."
        ),
    ),
    DocPage(
        slug="step-12",
        path="/docs/step-12",
        label="Step 12: Monitoring: Axiom, Sentry, the Health Check and the Status Dots",
        summary=(
            "Each line to Axiom once the request has answered; each error to Sentry, nothing private; the cache's own "
            "errors our warning; a health check of each lane, and a dot beside each in the picker."
        ),
    ),
    DocPage(
        slug="step-13",
        path="/docs/step-13",
        label="Step 13: Evals and Release: Golden Questions, a Load Test, Rollback",
        summary=(
            "Golden questions asked of the live site and graded by rules, kept in LangSmith; a small load test; how to "
            "roll back; the Technical details page; the TypeScript backup tag deleted."
        ),
    ),
    DocPage(
        slug="step-14",
        path="/docs/step-14",
        label="Step 14: Observability: Activity, Performance, Evaluations, Health, and the Menu in Groups",
        summary=(
            "The app's own lines read back from Axiom with a token that can only query, onto four pages anyone can "
            "open, nothing private on them; each query once a minute; and the menu's links in groups."
        ),
    ),
    DocPage(
        slug="step-15",
        path="/docs/step-15",
        label="Step 15: Activity by Request, and Rows That Lead to It",
        summary=(
            "Each request on Activity a row that opens onto its timeline, from its first line to its last, shown only "
            "by its ref; every tool, lane, ending, reason and day on the other pages a link to its requests."
        ),
    ),
)
CHAPTERS += (
    DocPage(
        slug="step-16",
        path="/docs/step-16",
        label="Step 16: Park Guidance with Retrieved Sources",
        summary=(
            "Official park guidance, retrieved for an exact destination alongside live weather, with source links; "
            "a versioned index built before deployment, optional embeddings, and evaluations of source evidence."
        ),
    ),
    DocPage(
        slug="step-17",
        path="/docs/step-17",
        label="Step 17: Official Park Notices",
        summary="Bounded official NPS checks alongside stored guidance, with a standalone page and chat citations.",
    ),
)
PAGES: tuple[DocPage, ...] = (
    DocPage(slug="architecture", path="/architecture", label="Architecture and design"),
    DocPage(slug="system-design", path="/system-design", label="System design"),
    DocPage(slug="technical-details", path="/technical-details", label="Technical details"),
    DocPage(slug="issues", path="/issues", label="Issues and fixes"),
    DocPage(slug="interview", path="/interview", label="Interview guide"),
    DocPage(slug="todo", path="/todo", label="To do"),
    DocPage(slug="waiting-on-you", path="/waiting-on-you", label="Waiting on you"),
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
