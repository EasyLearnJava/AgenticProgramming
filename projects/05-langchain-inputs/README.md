# 05 · Pass several inputs

Project 4 passed one input. This one passes three (a greeting, a name and a city) into one template, gives the
greeting a default with `prompt.partial()`, and allows only three greetings. Each bad field gets its own error,
shown next to that field. No model, no API key.

```text
Good morning Raghu from Dallas, welcome to LangChain!
```

## What you learn

- Several template variables: `{greeting} {name} from {city}`; `prompt.input_variables` lists all three
- `prompt.partial(greeting="Hello")`: fills one variable in ahead of time, so it becomes optional
- `Literal["Hello", "Good morning", "Namaste"]`: a field that accepts only fixed choices
- Per-field errors: one 422 lists every bad field, and `loc` says which field each error is about

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt.partial(greeting="Hello") \| to_text`. `python hello.py Asha Pune "Good morning"` |
| `main.py` | FastAPI: `GET /` (or `/index.html`) serves the page, `POST /api/hello` checks the body with `HelloIn` and runs the chain |
| `index.html` | The page: a greeting list, name and city boxes. Sends them as JSON; shows each 422 error next to its field |
| `tests/test_hello.py` | Tests the variables, the partial, the script, the endpoint, each bad field and all of them at once, and the page |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core` (Pydantic comes with FastAPI) |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## How `partial()` gives a default

```python
prompt = PromptTemplate.from_template("{greeting} {name} from {city}, welcome to LangChain!")
prompt.input_variables              # ['city', 'greeting', 'name']

prompt_with_default = prompt.partial(greeting="Hello")
prompt_with_default.input_variables # ['city', 'name']: greeting is filled in already

chain = prompt_with_default | to_text
chain.invoke({"name": "Raghu", "city": "Dallas"})                          # Hello Raghu from Dallas, ...
chain.invoke({"name": "Raghu", "city": "Dallas", "greeting": "Namaste"})   # Namaste Raghu from Dallas, ...
```

`partial()` returns a new prompt; `prompt` itself still needs all three. A greeting passed to `invoke()` replaces
the default. That is why the server leaves `greeting` out of the input when the page doesn't send one
(`body.model_dump(exclude_none=True)`).

## How a request flows

```text
fill in the form, click   →  fetch("/api/hello", POST, {"greeting": "Good morning", "name": "Raghu", "city": "Dallas"})
                             (greeting is left out when the list says "(default: Hello)")
FastAPI                   →  reads the JSON into HelloIn and checks every field
   ├─ any bad field       →  422 {"detail": [ one entry per bad field, each with loc ["body", "<field>"] ]}
   │                         the page writes each message next to its field
   └─ all good            →  hello(body)  →  await chain.ainvoke({...})
JSON back                 →  {"answer": "Good morning Raghu from Dallas, welcome to LangChain!"}
```

| You send | Server answers |
|---|---|
| greeting `Good morning`, name `Raghu`, city `Dallas` | `200` Good morning Raghu from Dallas, welcome to LangChain! |
| no greeting, name `Raghu`, city `Dallas` | `200` Hello Raghu from Dallas, welcome to LangChain! (the default) |
| greeting `Hi` | `422` for `greeting`: `literal_error`, "Pick Hello, Good morning or Namaste." |
| an empty (or spaces-only) name or city | `422` for that field: `string_too_short`, "Please fill this in." |
| a name or city over 40 characters | `422` for that field: `string_too_long`, "Too long: 40 characters at most." |
| several bad fields | `422` with one error for each, all shown at once |

The list's last choice, "Hi (not allowed)", is there so you can see the server refuse a greeting that isn't one of
the three. As in project 4, the boxes have no `maxlength` or `required`, so the server's checks are what you see.

## Run it

```bash
cd projects/05-langchain-inputs
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python hello.py                              # Hello Raghu from Dallas, welcome to LangChain!
python hello.py Asha Pune "Good morning"     # Good morning Asha from Pune, welcome to LangChain!
python -m pytest                             # 22 tests

uvicorn main:app --reload                    # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs → **POST /api/hello** → **Try it out** | `https://<codespace-name>-8000.app.github.dev/docs` |

`/api/hello` only accepts `POST`, so opening it in the address bar gives 405 Method Not Allowed. With curl:

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"greeting": "Namaste", "name": "Raghu", "city": "Dallas"}'
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"greeting": "Hi", "name": "", "city": ""}'          # three errors in one 422
```

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

The chain fills in text it is given. The next projects compose steps (side by side, branching, batches) before
the first real model call.
