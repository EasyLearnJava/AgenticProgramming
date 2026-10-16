# 04 · Pass one input

The chain takes an input for the first time: a name. You type it in a box, the page sends it to the server as
JSON, the server checks it, and the chain answers "Hello {name}, welcome to LangChain!". No model, no API key.

## What you learn

- A template variable: `{name}` in the template, filled in by `chain.invoke({"name": ...})`
- `POST` with a JSON body: the page sends `{"name": "Raghu"}`, not just a request for a fixed answer
- A Pydantic model: `HelloIn(name: str = Field(min_length=1, max_length=40))` describes the body
- `422` validation: FastAPI checks the body before your code runs, and the page turns its error into plain words

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `PromptTemplate("Hello {name}, …") \| to_text`. `python hello.py Raghu` runs it with a name |
| `main.py` | FastAPI: `GET /` (or `/index.html`) serves the page, `POST /api/hello` checks the body with `HelloIn` and runs the chain |
| `index.html` | The page: a name box and a button. On submit (click or Enter) it POSTs the name as JSON and shows the answer or a friendly error |
| `tests/test_hello.py` | Tests the variable, the chain, `hello.py` as a script, the endpoint, each kind of bad name, and the page |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core` (Pydantic comes with FastAPI) |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## How a request flows

```text
type "Raghu", click       →  fetch("/api/hello", POST, body {"name": "Raghu"})
FastAPI                   →  reads the JSON into HelloIn: trims spaces, checks 1-40 characters
   ├─ bad name            →  422 {"detail": [{"type": "string_too_short", ...}]}   hello() never runs
   │                         the page shows "Please type a name first."
   └─ good name           →  hello(body)  →  await chain.ainvoke({"name": "Raghu"})
JSON back                 →  {"answer": "Hello Raghu, welcome to LangChain!"} shown on the page
```

| You type | Server answers | The page shows |
|---|---|---|
| `Raghu` | `200` `{"answer": "Hello Raghu, welcome to LangChain!"}` | Hello Raghu, welcome to LangChain! |
| `  Raghu  ` | `200`, the spaces are trimmed | Hello Raghu, welcome to LangChain! |
| nothing, or only spaces | `422` `string_too_short` | Please type a name first. |
| 41 or more characters | `422` `string_too_long` | That name is too long: 40 characters at most. |

The name box has no `maxlength` or `required` on purpose: the server does the checking, so you can see the 422.
A real app would check in both places: in the page for a quick hint, and on the server because anyone can send
any request.

## Run it

```bash
cd projects/04-langchain-input
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python hello.py                    # Hello World, welcome to LangChain!
python hello.py Raghu              # Hello Raghu, welcome to LangChain!
python -m pytest                   # 16 tests

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs → **POST /api/hello** → **Try it out** | `https://<codespace-name>-8000.app.github.dev/docs` |

Opening `/api/hello` straight in the browser now gives `{"detail":"Method Not Allowed"}` (405): the address bar
always sends a `GET`, and this route only accepts `POST`. Use the page, `/docs`, or curl:

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Raghu"}'
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": ""}'   # the 422
```

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## See it working

DevTools (F12) → **Network** → click the `hello` request:

- **Payload** shows what the page sent: `{"name": "Raghu"}`
- **Response** shows the answer, or for an empty name the 422 with `string_too_short`

## Next

One input. The next project passes several: a greeting, a name and a city.
