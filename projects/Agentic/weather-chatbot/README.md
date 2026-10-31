# Nimbus: a Weather Chatbot, Rebuilt in Python

Nimbus answers questions about the weather anywhere, and shows each tool call behind an answer and the path it took.
Its first version was built in TypeScript; this is its rebuild in Python, with FastAPI, LangGraph and Jinja2, as a
production-grade app and a step-by-step tutorial at once. Each of its thirteen steps adds one idea, ends deployed and
working, and has a chapter written while it was built: the design, the code that matters, the pitfalls, the issues
met, and interview questions. Live at https://weather-chatbot-hazel.vercel.app/.

**In one line:** your browser → Vercel → the FastAPI app: the security headers, the request's id, the router → a page
from a Jinja2 template, JSON, or a question's answer, streamed as server-sent events of HTML that htmx puts into the
page → back to you, with its log lines. Gemini writes the answer, through LangChain (step 3), from what the
weather tools found: an agent calls them, and they call Open-Meteo (step 4).

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
| `nimbus/` | The app, one module per job: `app.py`, `config.py`, `constants.py`, `logger.py`, `middleware.py`, `pages.py`, `docs.py`, `health.py`, `chat.py`, `model.py`, `prompts.py`, `agent.py`, `answer.py`, `tools.py`, `open_meteo.py`, `weather.py`, `chips.py`, `errors.py`, `utils.py` |
| `templates/` | The Jinja2 templates: the shell with the menu, the chat and the HTML of its answer's events, a list of pages, a page, the 404 page |
| `public/static/` | The stylesheet, the icon, htmx 4 and its stream extension, and our `chat.js`, served by Vercel's CDN |
| `docs/` | The chapters (`step-N.md`), the system design, the issues log, the interview guide, the to-do list, the TypeScript version's pages (`*_deprecated.md`), and their pictures (`images/`) |
| `tests/unit/`, `tests/e2e/`, `tests/fixtures/` | The tests: the app called in memory, and the app in a real browser; Open-Meteo's recorded answers |
| `tools/mutation_check.py`, `tools/run_tool.py` | Breaks each of the app's rules on purpose, and checks a test fails; runs one weather tool on its own |
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
| 2 | [The Chat Streams Its Answer](docs/step-2.md) | Done |
| 3 | [Gemini Answers, Streamed](docs/step-3.md) | Done |
| 4 | [The Weather Tools, and an Agent That Calls Them](docs/step-4.md) | Done |
| 5 | The agent as a graph of our own | Next |
| 6 to 13 | See [PLAN.md](PLAN.md) | To come |

## Run it

```text
$ uv run uvicorn main:app --reload --no-access-log
INFO:     Will watch for changes in these directories: ['C:\\...\\weather-chatbot']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [28008] using StatReload
INFO:     Started server process [38936]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Then open http://127.0.0.1:8000 (the folder's path is shortened above). Each request writes one JSON line, with its id
and never its query string; this one is for `/docs?q=private`:

```json
{"method": "GET", "path": "/docs", "status": 200, "ms": 8, "event": "http.request", "level": "info",
 "ts": "2026-10-31T09:16:15.011594Z", "env": "local", "commit": null, "deploymentId": null,
 "requestId": "cc72b5f0a782411f"}
```

## Test it

```text
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
75 files already formatted
$ uv run mypy
Success: no issues found in 49 source files
$ uv run pytest
357 passed in 8.95s
$ uv run pytest tests/e2e --browser-channel msedge
121 passed in 90.67s (0:01:30)
$ uv run python tools/mutation_check.py
...
96 of 96 caught
```

`uv run pytest` runs the unit tests; `tests/e2e` serves the real app with Uvicorn and drives it in a browser, on all
24 pages and in the chat (leave out `--browser-channel msedge` to use Playwright's own Chromium). pytest also prints
its platform line and each test's dot, and the mutation check a line per rule (each chapter lists its own).

## When things go wrong

| You see | Why | What to do |
|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` | Starlette 1.8's test client prefers `httpx2` | `uv sync`: the dev group has `httpx2` (issue 1) |
| `error: Duplicate module named "conftest" (also at "tests\e2e\conftest.py")` | Two test folders without `__init__.py` | Keep the `__init__.py` files in `tests/` (issue 8) |
| `ModuleNotFoundError: No module named 'nimbus'` | A script run from another folder: Python looks in the script's folder, not yours | `PYTHONPATH=.` before the command (issue 6) |
| `Cannot navigate to invalid URL` with `C:/Program Files/Git/...` | Git Bash turned an argument starting with `/` into a Windows path | `MSYS_NO_PATHCONV=1` before the command (issue 6) |
| `The assistant isn't set up on this deployment yet.`, with `503` | No `GOOGLE_API_KEY`, or one Gemini refuses | Put your own key in `.env.local` and restart; on Vercel, set it in the project's settings and redeploy |
| `The chat couldn't read that request.`, with `415` | A question sent as JSON, or without the form's type | Send a form, `application/x-www-form-urlencoded`, as the page does; curl's `-d` does too |
| `ValidationError: 1 validation error for Settings` / `vercel_env` / `Input should be 'production', 'preview' or 'development'` | A setting with a value the app doesn't know, here `VERCEL_ENV=staging` | Fix or remove the value; the error names the setting |

## Things to try

- Add a chapter: a Markdown file in `docs/` and its `DocPage` in `CHAPTERS` (`nimbus/docs.py`); the tests say if
  you forget either. A page outside `/docs/`, in `PAGES`, also needs its route in `nimbus/pages.py`.
- Put `LOG_LEVEL=warning` in `.env.local`, restart, and watch the request lines stop.
- Send a forged id: `curl -i -H "x-vercel-id: not an id" http://127.0.0.1:8000/api/health` gets a new one back.
- Watch an answer stream: `curl -N --data-urlencode "question=Hi" http://127.0.0.1:8000/api/chat` prints each event
  as it comes (with your own `GOOGLE_API_KEY` in `.env.local`; without one, the chat says it isn't set up).
- Ask something off-topic: Gemini says, in one sentence, what it can do.
- Run a weather tool on its own, against Open-Meteo, with no key:
  `uv run python -m tools.run_tool get_air_quality '{"latitude": 28.61, "longitude": 77.21}'` (in bash).

## Documentation

The app explains itself: open **Documentation** in its menu, or read the same pages in [`docs/`](docs/): a chapter per
step ([step 1](docs/step-1.md), [step 2](docs/step-2.md), [step 3](docs/step-3.md), [step 4](docs/step-4.md)), the
**System design** ([`docs/system-design.md`](docs/system-design.md)), **Issues and fixes**
([`docs/issues.md`](docs/issues.md)), the **Interview guide** ([`docs/interview.md`](docs/interview.md)) and **To do**
([`docs/todo.md`](docs/todo.md)). The TypeScript version's pages are kept under **Deprecated**: its steps, System
design, Technical details, Issues and fixes, Interview guide and To do, each named `*_deprecated`
([README_deprecated.md](README_deprecated.md) links them all).

## Next

[Step 4's chapter](docs/step-4.md), then step 5: the agent as a LangGraph graph of our own.
