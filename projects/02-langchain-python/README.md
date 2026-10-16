# 02 · LangChain basic (Python)

Project 1's chain (a `PromptTemplate` piped into a `RunnableLambda`), rewritten in Python and served by FastAPI,
which is how production apps run LangChain: on a server. No model, no API key.

## What you learn

- `langchain-core` in Python: the same `PromptTemplate` and `RunnableLambda` as project 1
- `|`: Python's `.pipe()`, joins one Runnable to the next
- `ainvoke()`: the async twin of `invoke()`, used inside a server route
- A FastAPI `GET` route, served by `uvicorn`
- A page that calls the server as soon as it opens: browser → `GET /api/hello` → chain → answer on the page

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt \| to_text`. Run it on its own with `python hello.py` |
| `main.py` | FastAPI: `GET /` (or `/index.html`) serves the page, `GET /api/hello` runs the chain with `await chain.ainvoke({})` and returns JSON |
| `index.html` | The page: on load, `fetch("/api/hello")` and show the answer |
| `tests/test_hello.py` | Tests the chain, the prompt's object vs `to_text`'s string, `hello.py` as a script, the endpoint and the page |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## How a request flows

```text
open the page (GET /)  →  main.py sends index.html
page loads             →  fetch("/api/hello")
main.py                →  await chain.ainvoke({})   (the chain from hello.py)
JSON back              →  the page shows "Hello World, welcome to LangChain!"
```

## Run it

```bash
cd projects/02-langchain-python
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python hello.py                    # just the chain: Hello World, welcome to LangChain!
python -m pytest                   # 6 tests

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page (calls the server on load) | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| The raw JSON | http://127.0.0.1:8000/api/hello | `https://<codespace-name>-8000.app.github.dev/api/hello` |
| FastAPI's API docs | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

In Codespaces, `127.0.0.1` is the codespace, not your laptop. Use the forwarded address instead: open the **Ports**
tab next to **Terminal** and click the globe icon on port 8000, or click **Open in Browser** in the pop-up that
appears when the server starts. `<codespace-name>` is the first part of the codespace's own address, for example
`orange-succotash-gw4799ggp42vqv` in `orange-succotash-gw4799ggp42vqv.github.dev`.

The server builds the chain once at start; `--reload` restarts it when you edit `hello.py` or `main.py`.
Refresh the page to call the server again.

## Next

The chain runs once, by itself. The next project runs it only when asked.
