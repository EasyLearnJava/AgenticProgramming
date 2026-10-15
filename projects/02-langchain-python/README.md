# 02 · LangChain basic (Python)

Project 1's chain (a `PromptTemplate` piped into a `RunnableLambda`), rewritten in Python and served by FastAPI,
which is how production apps run LangChain: on a server. No model, no API key.

## What you learn

- `langchain-core` in Python: the same `PromptTemplate` and `RunnableLambda` as project 1
- `|`: Python's `.pipe()`, joins one Runnable to the next
- `ainvoke()`: the async twin of `invoke()`, used inside a server route
- A FastAPI `GET` route, served by `uvicorn`

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt \| to_text`. Run it on its own with `python hello.py` |
| `main.py` | FastAPI: `GET /api/hello` runs the chain with `await chain.ainvoke({})` and returns JSON |
| `tests/test_hello.py` | Tests the chain, the prompt's object vs `to_text`'s string, `hello.py` as a script, and the endpoint |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## Run it

```bash
cd projects/02-langchain-python
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python hello.py                    # Hello World, welcome to LangChain!
python -m pytest                   # 4 tests

uvicorn main:app --reload          # the server on http://127.0.0.1:8000
curl http://127.0.0.1:8000/api/hello
```

The server builds the chain once at start, so `--reload` restarts it when you edit `hello.py`.
In GitHub Codespaces, open the forwarded port 8000 and add `/api/hello` to the address to see the JSON.

## Next

The chain runs once, by itself. The next project runs it only when asked.
