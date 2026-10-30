# Nimbus: a Weather Chatbot, Rebuilt in Python

Nimbus answers questions about the weather anywhere, and shows each tool call behind an answer and the path it took.
Its first version was built in TypeScript; this is its rebuild in Python, with FastAPI, LangGraph and Jinja2, as a
production-grade app and a step-by-step tutorial at once. Each of its thirteen steps adds one idea, ends deployed and
working, and has a chapter written while it was built: the design, the code that matters, the pitfalls, the issues
met, and interview questions. Live at https://weather-chatbot-hazel.vercel.app/.

**In one line:** your browser → Vercel → the FastAPI app: the security headers, the request's id, the router → a page
from a Jinja2 template, or JSON → back to you, with one log line. (From step 2, answers stream in; from step 4, an
agent calls the weather tools.)

## What you'll build

Step by step: a FastAPI app with Nimbus's pages and docs (step 1); a chat that streams its answer with HTMX (2); answers
from Gemini through LangChain (3); a LangGraph agent with four weather tools (4, 5); chat memory kept in the browser (6)
and a weather cache (7); our own MCP server (8) and a lane through it (9); two lanes through Apify, with fallbacks (10);
then security (11), monitoring (12), and evals and the release (13). The full roadmap is in [PLAN.md](PLAN.md).

## What you'll learn

How to build an AI agent app the way it's run in production: FastAPI, Jinja2 and HTMX for the pages; LangChain and
LangGraph for the agent; MCP for its tools; Pydantic at every edge; structured logs with a request id; security
headers and an enforced Content Security Policy; tests in memory, in a real browser and for accessibility, with a
mutation check; and CI and deploys to Vercel on every push.

## Before you start

- **Python 3.13** and **uv** 0.9 or newer (`uv --version`), and Git.
- **For the browser tests:** Edge or Chrome on your computer, or `uv run playwright install chromium`.
- In this folder, `uv sync` makes `.venv/` and installs every package at the version `uv.lock` pins.
- Settings for your computer go in `.env.local` (copy `.env.example`); git never sees it.

## Files

| File or folder | What it holds |
|---|---|
| `main.py` | The entry point: `app = create_app()`, which Vercel and Uvicorn both look for |
| `nimbus/` | The app, one module per job: `app.py`, `config.py`, `constants.py`, `logger.py`, `middleware.py`, `pages.py`, `docs.py`, `health.py`, `utils.py` |
| `templates/` | The Jinja2 templates: the shell with the menu, the chat, a list of pages, a page, the 404 page |
| `public/static/` | The stylesheet and the icon, served by Vercel's CDN |
| `docs/` | The chapters (`step-N.md`), the issues log, the interview guide, the to-do list, the TypeScript version's pages (`*_deprecated.md`), and their pictures (`images/`) |
| `tests/unit/`, `tests/e2e/` | The tests: the app called in memory, and the app in a real browser |
| `tools/mutation_check.py` | Breaks each of the app's rules on purpose, and checks a test fails |
| `pyproject.toml`, `uv.lock`, `.python-version` | The packages, pinned to exact versions; the tools' settings; Python 3.13 |
| `vercel.json` | The CDN's files' security headers; the tests and tools left out of the function Vercel builds |
| `PLAN.md` | The roadmap, the chapter template, the code standards and the rules |
| `README_deprecated.md`, `PLAN_deprecated.md` | The TypeScript version's README and plan, kept |

CI is at the repository's root, in `.github/workflows/weather-chatbot.yml`.

## How it works

Each step's chapter explains it, in order:

| Step | Chapter | Status |
|---|---|---|
| 1 | [The Project, Its Pages and Its First Deploy](docs/step-1.md) | Done |
| 2 | The chat streams its answer, with HTMX | Next |
| 3 to 13 | See [PLAN.md](PLAN.md) | To come |

## Run it

```text
$ uv run uvicorn main:app --reload --no-access-log
INFO:     Will watch for changes in these directories: ['C:\\...\\weather-chatbot']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [36760] using StatReload
INFO:     Started server process [3920]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Then open http://127.0.0.1:8000 (the folder's path is shortened above). Each request writes one JSON line, with its id
and never its query string; this one is for `/docs?q=private`:

```json
{"method": "GET", "path": "/docs", "status": 200, "ms": 13, "event": "http.request", "level": "info",
 "ts": "2026-10-30T23:07:18.495927Z", "env": "local", "commit": null, "deploymentId": null,
 "requestId": "6fcf320b485d4f78"}
```

## Test it

```text
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
48 files already formatted
$ uv run mypy
Success: no issues found in 26 source files
$ uv run pytest
117 passed in 1.00s
$ uv run pytest tests/e2e --browser-channel msedge
89 passed in 52.69s
$ uv run python tools/mutation_check.py
...
16 of 16 caught
```

`uv run pytest` runs the unit tests; `tests/e2e` serves the real app with Uvicorn and drives it in a browser, on all
21 pages (leave out `--browser-channel msedge` to use Playwright's own Chromium). pytest also prints its platform line
and each test's dot, and the mutation check a line per rule (step 1's chapter lists them).

## When things go wrong

| You see | Why | What to do |
|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` | Starlette 1.8's test client prefers `httpx2` | `uv sync`: the dev group has `httpx2` (issue 1) |
| `error: Duplicate module named "conftest" (also at "tests\e2e\conftest.py")` | Two test folders without `__init__.py` | Keep the `__init__.py` files in `tests/` (issue 8) |
| `ModuleNotFoundError: No module named 'nimbus'` | A script run from another folder: Python looks in the script's folder, not yours | `PYTHONPATH=.` before the command (issue 6) |
| `Cannot navigate to invalid URL` with `C:/Program Files/Git/...` | Git Bash turned an argument starting with `/` into a Windows path | `MSYS_NO_PATHCONV=1` before the command (issue 6) |
| `ValidationError: 1 validation error for Settings` / `vercel_env` / `Input should be 'production', 'preview' or 'development'` | A setting with a value the app doesn't know, here `VERCEL_ENV=staging` | Fix or remove the value; the error names the setting |

## Things to try

- Add a page: a Markdown file in `docs/` and its `DocPage` in `nimbus/docs.py`; the tests say if you forget either.
- Put `LOG_LEVEL=warning` in `.env.local`, restart, and watch the request lines stop.
- Send a forged id: `curl -i -H "x-vercel-id: not an id" http://127.0.0.1:8000/api/health` gets a new one back.

## Documentation

The app explains itself: open **Documentation** in its menu, or read the same pages in [`docs/`](docs/): a chapter
per step ([step 1](docs/step-1.md)), **Issues and fixes** ([`docs/issues.md`](docs/issues.md)), the **Interview
guide** ([`docs/interview.md`](docs/interview.md)) and **To do** ([`docs/todo.md`](docs/todo.md)). The TypeScript
version's pages are kept under **Deprecated**: its steps, System design, Technical details, Issues and fixes,
Interview guide and To do, each named `*_deprecated` ([README_deprecated.md](README_deprecated.md) links them all).

## Next

[Step 1's chapter](docs/step-1.md), then step 2: the chat streams its answer.
