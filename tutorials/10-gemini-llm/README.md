# 10 · First real LLM call

A script and a small web page where Gemini writes a welcome for any name: the first chain in this repo that calls a
real model, with the key from project 9. It takes the same `{name}` input as project 4, but ask twice and you'll
usually get two different answers, because a model writes them, not a template.

```text
{"name": "Asha"}  ->  "Welcome to the world of LangChain, Asha! We're excited to see what you'll build."
{"name": "Asha"}  ->  "Hi Asha, welcome aboard! LangChain is a great place to start building with LLMs."
                      (made-up examples: Gemini's words change every time)
{"name": ""}      ->  a 422, and no call to Gemini: a bad name costs nothing
```

## What you'll build

- **`hello.py`**: a three-step chain, `prompt | model | parser`, with Gemini as the middle step.
  `python hello.py Asha` prints a welcome that Gemini wrote for Asha.
- **`main.py`**: a FastAPI server. `POST /api/hello` with `{"name": "Asha"}` answers `{"answer": "..."}`. A bad name
  gets a 422 before any call; a failed call gets a 502.
- **`index.html`**: a name box and an **Ask Gemini** button. Each click is one real call.
- **Tests** that run with no key and no network, plus a live test that calls Gemini.

## What you'll learn

- **`ChatGoogleGenerativeAI`**: Gemini as a step in a chain, from `langchain-google-genai`; each run of the chain is one call.
- **A chat model's input**: the prompt's text reaches Gemini as one `HumanMessage`, so no `to_text` step is needed.
- **`StrOutputParser`**: the model answers with an `AIMessage`; the parser keeps just the text.
- **`max_output_tokens`**: a cap on each answer's length, and so on its cost.
- **Errors from a real service**: a 422 before the call costs nothing; a failed call is a 502, its reason kept on the server.
- **Plain and live tests**: a stand-in chain lets most tests run with no call; a `@pytest.mark.live` test calls Gemini.

## What's new since project 09

- [Project 09 · Get a Gemini key and keep it secret](../09-gemini-key/README.md) made the key, and its code only
  checked that the key was set. Now `hello.py` hands it to Gemini, and the fail-fast check moves with it: from
  `main.py` ("Can't start the server") to `hello.py` ("Can't build the chain"), so the script and the server both
  stop without a key.
- The chain is back, now with a model in it: `prompt | model | parser`. Project 7's two paths each ended in
  `to_text`; here the parser gives back the text, after the model.
- `GET /api/status` is gone. `POST /api/hello` is back, with project 4's `{"name"}` body and `{"answer"}` reply, plus
  a 502 when Gemini fails.
- New packages: `langchain-core`, `langchain-google-genai` and `google-genai`. New test pieces: `tests/conftest.py`
  and the `live` marker in `pytest.ini`.

## Before you start

- Python 3.11 or newer.
- The key from [project 9](../09-gemini-key/README.md). Each project folder reads its own `.env`, so copy yours into
  this one, once. From this folder, `tutorials/10-gemini-llm`:

  ```bash
  cp ../09-gemini-key/.env .env
  ```

  With a Codespaces secret named `GOOGLE_API_KEY` there's nothing to copy: every project sees it.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt \| model \| parser`. `python hello.py [name]` makes one real call |
| `main.py` | FastAPI: `GET /` and `/index.html` serve the page; `POST /api/hello` runs the chain. A bad name gets a 422 before any call; a failed call gets a 502 |
| `index.html` | The page: a name box and an **Ask Gemini** button |
| `config.py` | `load_api_key()`: loads `.env`, checks the key, and raises `MissingKeyError` with a clear message when there's none. The same file as project 9 |
| `.env.example` | The template for `.env`, the file that holds your key. `.env` is in `.gitignore`, so it never goes into git |
| `tests/test_hello.py` | The tests: plain ones that make no call, and a live one that makes a real call |
| `tests/conftest.py` | Runs before the tests and checks once for a real key: with none, it gives `hello.py` a fake one and skips the live test |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, only looks in `tests/`, and defines the `live` marker |
| `requirements.txt` | The packages, pinned: `fastapi`, `uvicorn`, `langchain-core`, `langchain-google-genai`, `google-genai` (Google's own library, which `langchain-google-genai` uses underneath) and `python-dotenv` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |
| `README.md` | This page |

## How it works

### ① The key

```python
# ① The key, checked first (project 9). No key, no chain.
try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")
```

`load_api_key()` is project 9's: it reads `GOOGLE_API_KEY` from the environment or from `.env`, and raises
`MissingKeyError` when there's no usable key. `hello.py` checks the key before it builds anything, and `main.py`
imports `hello.py`, so `python hello.py` and `uvicorn main:app` both stop at once without a key: just the message,
no stack trace.

### ② The prompt

```python
# ② The prompt: the same kind of template as before. The text it makes is now an instruction for the model.
prompt = PromptTemplate.from_template(
    "Write a short, friendly welcome for {name}, who is starting to learn LangChain. One or two sentences."
)
```

Up to project 7, the template's text was the answer. Now it's an **instruction** for the model.
`prompt.invoke({"name": "Asha"})` gives a `StringPromptValue` holding that instruction, with Asha in it.

### ③ The model

```python
MODEL = "gemini-3.5-flash-lite"   # small, fast and cheap: the one place the code names the model (a test checks it)
MAX_OUTPUT_TOKENS = 200           # a cap on the length of each answer, and so on its cost
...
# ③ The model. Building it makes no call: the call happens each time the chain runs.
#    The key goes in here and only here. The model keeps it as a SecretStr, which prints as '**********'.
#    It takes the prompt's output as it is: a chat model turns the StringPromptValue into one HumanMessage
#    (a chat message from the user), so no to_text step is needed between them.
model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)
```

- **Building `model` makes no call and costs nothing.** Each run of the chain makes one call.
- **The key stays hidden.** The model keeps it as a `SecretStr`: `print(model.google_api_key)` shows `**********`.
- **A chat model reads messages.** The model turns the prompt's `StringPromptValue` into one message from the user,
  `[HumanMessage(content='Write a short, friendly welcome for Asha, who is starting to learn LangChain. One or two sentences.')]`,
  and sends that to Gemini. Project 13 writes the messages itself, with `ChatPromptTemplate`.
- **`max_output_tokens`** caps how long each answer can be, in tokens (the pieces of text a model reads and writes).
  A longer answer costs more, so the cap also caps the cost. Project 11 counts the tokens.
- **It retries by itself.** When a call fails for a reason that may pass (no network, too many requests), the model
  tries again with growing pauses, up to 6 tries in all (`max_retries`). A request that can never work, such as one
  with a wrong key, fails at once.

### ④ The parser and ⑤ the chain

```python
# ④ The parser: the model gives back an AIMessage (text plus details); this keeps just the text.
#    It takes the place of the to_text step from projects 2 to 7.
parser = StrOutputParser()

# ⑤ The chain, built with | as before.
chain = prompt | model | parser
```

| Step | In | Out |
|---|---|---|
| `prompt` | `{"name": "Asha"}` | a `StringPromptValue`: the instruction, with Asha in it |
| `model` | the `StringPromptValue`, which it turns into one `HumanMessage` | an `AIMessage`: the text, plus details like token counts |
| `parser` | the `AIMessage` | just the text, a `str` |

Running the chain is one call to Gemini. That's what `python hello.py` does:

```python
if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    print(chain.invoke({"name": name}))
```

### The server

```python
class HelloIn(BaseModel):
    """The JSON body: one name. Checked before the model is called, so a bad name costs nothing."""
    # model_config holds Pydantic's settings for this class: nothing to do with the Gemini model.
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Asha " -> "Asha", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)
...
@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain once: one real call to Gemini."""
    try:
        # ainvoke() is invoke()'s async twin (project 4): while Gemini writes, the server can serve other requests.
        answer = await chain.ainvoke({"name": body.name})
    except Exception as err:
        # The full reason goes to the server's terminal; the page only learns that the model didn't answer.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
    return {"answer": answer}
```

- **A bad name never reaches Gemini.** FastAPI checks the body against `HelloIn` before `hello()` runs: an empty
  name, only spaces, or more than 40 characters gets a **422**, and no call is made.
- **A failed call becomes a 502** ("bad gateway": this server is fine, but the service behind it didn't answer).
  The page gets only the error's type, such as `Gemini didn't answer (GoogleInvalidRequestError).`, and never the
  details: those stay in the server's terminal. `logger` is uvicorn's own logger, so its lines appear among
  uvicorn's messages.

### The page

```js
        // A 422 (a bad name) and a 502 (Gemini didn't answer) come back with a JSON "detail" that this page shows.
        // Any other error status is unexpected: jump to the catch below.
        if (!res.ok && res.status !== 422 && res.status !== 502) {
          throw new Error(`the server answered HTTP ${res.status}`);
        }
        const data = await res.json();
        if (res.status === 422) {
          // FastAPI lists each problem with where it is (loc, ending in the field's name) and what's wrong (msg).
          answer.textContent = data.detail.map((p) => `${p.loc.at(-1)}: ${p.msg}`).join("; ");
        } else if (res.status === 502) {
          answer.textContent = `${data.detail} The server's terminal says why.`;
        } else {
          answer.textContent = data.answer;
        }
```

Each submit sends `{"name": ...}` to `POST /api/hello`; the page itself never sees the key. The button stays
disabled until the answer is back: one paid call at a time.

| The server answers | The page shows |
|---|---|
| 200 | the welcome |
| 422 | what was wrong, for example `name: String should have at least 1 character` |
| 502 | `Gemini didn't answer (GoogleInvalidRequestError). The server's terminal says why.` |
| any other status, or nothing at all | `Something went wrong: the server answered HTTP 500`, or `Something went wrong: Failed to fetch` |

## Run it

```bash
cd tutorials/10-gemini-llm
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the `.env` copied in (see [Before you start](#before-you-start)):

```bash
python config.py                     # GOOGLE_API_KEY is set.  (or a message saying what to do)
python hello.py                      # a welcome for Raghu, written by Gemini: one real call
python hello.py Asha                 # one for Asha
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

The curl examples are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha"}'
# {"answer":"..."}   Gemini's welcome: one real call, new words every time

curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": ""}'
# {"detail":[{"type":"string_too_short","loc":["body","name"],"msg":"String should have at least 1 character",...}]}
# a 422, and no call to Gemini
```

Every click and every `curl` with a good name is a real call to Gemini, and uses your key's quota.

## Test it

```bash
python -m pytest                     # every test; the live one is skipped when there's no key
python -m pytest -m "not live"       # only the plain tests: no call, no cost
python -m pytest -m live             # only the live test: one real call
```

There are 15 tests: 14 plain and 1 live.

- **The 14 plain tests** never call Gemini:
  - the chain's parts (5): the prompt's text, the order (prompt, then model, then parser), the model's name and
    cap, the key hidden as a `SecretStr`, and the parser
  - no key (2): `python hello.py` and `uvicorn main:app` stop with the message and no traceback
  - the endpoint (5): the answer comes back, with the spaces trimmed off the name; an empty name and a 41-character
    name each get a 422, and the chain never runs; a failed call gets a 502 with only the error's type, while the
    full reason goes to the server's log; and `GET /api/hello` gets a 405
  - the page (2): `/` and `/index.html` are served, with no key in them
- **The live test** makes one real call through `POST /api/hello` and checks the **shape** of the answer: a
  non-empty string, shorter than 1,000 characters, with "Asha" in it and no key. It can't check the exact words,
  because they change every time.

For the endpoint tests, the chain is swapped for a small stand-in,
`monkeypatch.setattr(main, "chain", RunnableLambda(...))`, so they need no key and no network. `tests/conftest.py`
runs first and checks once for a real key. With one, every test runs. With none, it gives `hello.py` a fake key so
it can be imported, and skips the live test with `live test: needs GOOGLE_API_KEY (see project 9)`.

Without a key, `python -m pytest` ends with `14 passed, 1 skipped`, and `python -m pytest -m "not live"` with
`14 passed, 1 deselected`.

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No key: the `.env` isn't in this folder | `python hello.py` and `uvicorn main:app` stop at once with `Can't build the chain: GOOGLE_API_KEY is not set. ...`. With `--reload`, the message appears but the command keeps running, still saying `Uvicorn running on ...`, and the page won't open | Copy the `.env` in (see [Before you start](#before-you-start)). With `--reload`, press Ctrl+C and start the server again: it restarts by itself only when a `.py` file changes |
| A wrong key, on the page or with `curl` | A 502 at once. The page says `Gemini didn't answer (GoogleInvalidRequestError). The server's terminal says why.`, and the terminal says `WARNING:  Gemini call failed: Error calling model 'gemini-3.5-flash-lite' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. ...` | Fix the key in `.env`, then restart the server. If the key is a Codespaces secret, fix it on GitHub, stop and restart the codespace (it loads its secrets when it starts), then start the server again |
| A wrong key, with `python hello.py` | A long traceback: the script doesn't catch errors. Its last line says what went wrong: `langchain_google_genai.chat_models.GoogleInvalidRequestError: Error calling model 'gemini-3.5-flash-lite' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. ...` | Fix the key in `.env` (for a Codespaces secret, see the row above), then run it again |
| No quota left | After about half a minute of retries, a 502 with `(GoogleRateLimitError)`. The terminal says `429 RESOURCE_EXHAUSTED` | Wait and try again later. If you lowered the quota in [project 9](../09-gemini-key/README.md), you can raise it again in the same place |
| No network | `Asking Gemini…` for about 45 seconds while the model retries, then a 502 with `(ConnectError)` | Check your connection, then try again |
| `python hello.py > welcome.txt` (or a pipe) on Windows | `UnicodeEncodeError: 'charmap' codec can't encode character ...`, when the answer has a character, such as an emoji, that Windows' old text encoding can't write | Run `export PYTHONUTF8=1` (Git Bash) or `$env:PYTHONUTF8 = "1"` (PowerShell) first, or print straight to the terminal |

The first call in each run also prints this warning in the terminal (the server's version says `AsyncModels`):

```text
Direct use of automatic function calling (AFC) in Models.generate_content is not recommended. ...
```

It comes from `google-genai`, the library under `langchain-google-genai`. AFC lets that library call Python functions
you hand it as tools. This project hands it none, so the warning changes nothing.

## Things to try

1. **Change the instruction.** In `hello.py`, end the template with `Answer in French.` and run
   `python hello.py Asha`: Gemini follows the new instruction. Then run `python -m pytest -m "not live"`:
   `test_prompt_puts_the_name_into_the_instruction` fails, because it pins the exact prompt. Put the text back, or
   update the test to match.
2. **Lower the cap.** Set `MAX_OUTPUT_TOKENS = 10` and run `python hello.py`: the welcome comes back cut short.
   `test_model_settings` fails while you try it, because it checks that the cap is 200, so put it back afterwards.
   Project 11 puts this cap in a box on the page and shows the token counts.
3. **Break the key on purpose.** Add an `X` to the end of the key in `.env`, restart the server and click **Ask
   Gemini**. The page says `Gemini didn't answer (GoogleInvalidRequestError). The server's terminal says why.`, and
   the terminal says `API key not valid`. Put the key back and restart.

## Next

**[Project 11 · Tokens and cost](../11-gemini-tokens/README.md)**: the same welcome, plus the numbers behind each
call: the tokens in and out, how long it took, and what it would cost.
