# 10 · First real LLM call

The same `{name}` input as project 4, but now Gemini writes the greeting. Click twice and you get two different
answers: it's a real model, not a template.

```text
{"name": "Asha"}  ->  "Welcome to the world of LangChain, Asha! We're excited to see what you'll build."
{"name": "Asha"}  ->  "Hi Asha, welcome aboard! LangChain is a great place to start building with LLMs."
                      (made-up examples: the real words are different on every call)
```

## What you learn

- **`ChatGoogleGenerativeAI`**: Gemini as a step in a chain, from the `langchain-google-genai` package
- **`StrOutputParser`**: the model answers with a message object; the parser keeps just the text
- **`max_output_tokens`**: a cap on each answer's length, and so on its cost
- **Plain tests and live tests**: most tests make no call; one `@pytest.mark.live` test calls Gemini for real

## Before you start: the key

This project needs the key from [project 9](../09-gemini-key/README.md). Each project folder has its own `.env`,
so copy it across (or use a Codespaces secret, which every project sees):

```bash
cd projects/10-gemini-llm
cp ../09-gemini-key/.env .env      # or: cp .env.example .env, then put your key in it
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt \| model \| parser`. `python hello.py [name]` makes one real call |
| `config.py` | Loads and checks the key: the same file as project 9 |
| `main.py` | FastAPI: `GET /` serves the page, `POST /api/hello` runs the chain. A bad name gets a 422 before any call; a failed call gets a 502 |
| `index.html` | The page: a name box and an **Ask Gemini** button |
| `.env.example` | The template for `.env` |
| `tests/conftest.py` | Checks once for a real key: with none, it gives `hello.py` a fake one and skips the live test |
| `tests/test_hello.py` | 14 plain tests (no call) and 1 live test (one real call) |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core`, `langchain-google-genai`, `google-genai`, `python-dotenv` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## The chain

```python
prompt = PromptTemplate.from_template(
    "Write a short, friendly welcome for {name}, who is starting to learn LangChain. One or two sentences."
)
model = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=api_key, max_output_tokens=200)
parser = StrOutputParser()

chain = prompt | model | parser
```

| Step | In | Out |
|---|---|---|
| `prompt` | `{"name": "Asha"}` | the instruction, with Asha in it |
| `model` | the instruction | an `AIMessage`: the text, plus details like token counts |
| `parser` | the `AIMessage` | just the text, a `str` |

What changed since project 4: the template's text used to be the answer, and is now an **instruction** for the
model. The model step is new. The parser takes the place of the `to_text` step from projects 2 to 7.

Building `model` makes no call and costs nothing. Each `chain.invoke(...)` makes one call. The key goes into the
model and nowhere else, and the model keeps it as a `SecretStr`: `print(model.google_api_key)` shows `**********`.

## When things go wrong

| What happens | What you see |
|---|---|
| No key | `python hello.py` and `uvicorn main:app` stop at once: `Can't build the chain: GOOGLE_API_KEY is not set. ...` |
| An empty or too long name | A 422, and Gemini is never called: a bad request costs nothing |
| A wrong key, no quota left, no network | A 502: the page says `Gemini didn't answer (GoogleInvalidRequestError).`, and the server's terminal says why, for example `API key not valid` |

The page gets only the error's type and never the details: those stay in the server's terminal.

You may also see `Direct use of automatic function calling (AFC) ... is not recommended` in the terminal. That's
the `google-genai` library talking to itself, and it does no harm.

## Two kinds of tests

```bash
python -m pytest                   # all: 14 plain + 1 live (the live one is skipped when there is no key)
python -m pytest -m "not live"     # only the plain ones: no call, no cost
python -m pytest -m live           # only the live one: one real call
```

- **Plain tests** check everything that isn't the model: the prompt's text, the model's settings, that the key is
  hidden, the parser, the 422, the 502, and the page. For the endpoint tests, the chain is swapped for a tiny
  stand-in (`monkeypatch.setattr(main, "chain", ...)`), so they run with no key and no network.
- **The live test** calls Gemini once through `POST /api/hello` and checks the **shape** of the answer: a short,
  non-empty string with the name in it. It can't check the exact words, because they change every time.

## Run it

```bash
cd projects/10-gemini-llm
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../09-gemini-key/.env .env      # the key, once (see above)

python hello.py                    # a welcome for Raghu, written by Gemini
python hello.py Asha               # one for Asha
python -m pytest                   # 15 tests

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha"}'
```

Every click and every `curl` is a real call to Gemini, and uses your key's quota.

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

What does each call cost? The next project shows the tokens in and out, the price per call, and what
`temperature` does.
