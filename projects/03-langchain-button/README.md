# 03 · Run on a button click

Project 2's chain and server, unchanged. Only the page changes: nothing runs when it opens, and each click of a
button calls the server once. No model, no API key.

## What you learn

- A `click` event → `fetch`: the request moves out of page load and into a click handler
- A loading state: the page says "Asking the server…" while it waits
- A disabled button: no second click while a request is still running
- `cache: "no-store"`: every click is a real request to the server

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain, same as project 2: `prompt \| to_text` |
| `main.py` | FastAPI, same as project 2: `GET /` (or `/index.html`) serves the page, `GET /api/hello` runs the chain |
| `index.html` | The page: a button, the answer and a click counter. `fetch("/api/hello")` runs only inside the click handler |
| `tests/test_hello.py` | Tests the chain, `hello.py` as a script, the endpoint, the page, and that `fetch` is only in the click handler |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## How a request flows

```text
open the page (GET /)  →  main.py sends index.html; nothing else happens
click the button       →  button disabled, "Asking the server…", fetch("/api/hello")
main.py                →  await chain.ainvoke({})   (the chain from hello.py)
JSON back              →  the page shows "Hello World, welcome to LangChain!", button enabled again
```

## Run it

```bash
cd projects/03-langchain-button
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python hello.py                    # just the chain: Hello World, welcome to LangChain!
python -m pytest                   # 7 tests

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page (click to call the server) | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| The raw JSON | http://127.0.0.1:8000/api/hello | `https://<codespace-name>-8000.app.github.dev/api/hello` |

Only one server can use port 8000: stop project 2's server (Ctrl+C) before starting this one, or start this one on
another port with `uvicorn main:app --reload --port 8001` (and use `-8001` in the Codespaces address).

## See it working

Open the browser's DevTools (F12) → **Network** tab, then load the page:

1. On load: only the page itself is requested. There is no `hello` request.
2. Click once: one `hello` request, and the answer appears.
3. Click twice: two more `hello` requests, and the counter says 3.

The uvicorn terminal shows the same: one `GET /api/hello` line per click.

## Next

The chain always says the same thing. The next project passes it an input: a name.
