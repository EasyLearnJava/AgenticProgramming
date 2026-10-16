# 07 · Branch and batch a chain

Two more ways to compose a chain. `RunnableBranch` sends different inputs down different paths: a formal or a
casual greeting, picked from the input's `style`. `batch()` runs a whole list of inputs in one call, a few at a
time. No model, no API key.

```text
{"name": "Raghu", "style": "formal"}  ->  Good day, Raghu. Welcome to LangChain.
{"name": "Raghu", "style": "casual"}  ->  Hey Raghu! Welcome to LangChain!
```

## What you learn

- `RunnableBranch((condition, path), …, default)`: the first condition that is true picks the path
- `chain.batch([...])`: a list of inputs in, a list of answers out, in the same order
- `config={"max_concurrency": 3}`: at most 3 inputs run at the same time
- What LangChain adds over a plain `if` and a `for` loop

## Files

| File | What it is |
|---|---|
| `hello.py` | The two paths, `is_formal()`, the branch, and `greet_with_if()` (the same without LangChain). `python hello.py` runs both styles and a batch |
| `main.py` | FastAPI: `GET /` serves the page, `POST /api/hello` runs one input, `POST /api/batch` runs a list with `abatch()` |
| `index.html` | The page: a name with a formal/casual choice, and a box of `name,style` lines sent as one batch |
| `tests/test_hello.py` | Tests each path, the branch, its default, `batch()`, that `max_concurrency` really caps it, the plain `if`, the script, both endpoints and the page |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## The branch

```python
formal_chain = PromptTemplate.from_template("Good day, {name}. Welcome to LangChain.") | to_text
casual_chain = PromptTemplate.from_template("Hey {name}! Welcome to LangChain!") | to_text

def is_formal(inputs: dict) -> bool:
    return inputs["style"] == "formal"

chain = RunnableBranch(
    (is_formal, formal_chain),   # (condition, path): checked in order
    casual_chain,                # the default: when no condition is true
)
```

The branch gets the whole input, `{"name": "Raghu", "style": "formal"}`, gives it to each condition in turn, and
runs the first path whose condition says `True`. The chosen path gets the same whole input; its template uses only
`{name}`. Any style other than `"formal"` takes the default path: `chain.invoke({"name": "Raghu", "style": "loud"})`
says "Hey Raghu!". The server is stricter: `HelloIn` allows only `"formal"` and `"casual"`, so `"loud"` gets a 422
there.

More paths are more pairs: `RunnableBranch((is_formal, formal_chain), (is_pirate, pirate_chain), casual_chain)`.

## The batch

```python
chain.batch(
    [{"name": "Raghu", "style": "formal"}, {"name": "Asha", "style": "casual"}, ...],   # five people
    config={"max_concurrency": 3},
)
# ["Good day, Raghu. Welcome to LangChain.", "Hey Asha! Welcome to LangChain!", ...]   five answers, same order
```

Each input goes through the branch on its own, so one batch can mix styles. `max_concurrency` caps how many run at
the same time; a test checks that eight slow inputs with `max_concurrency=3` never have more than three running.
With instant steps like these you won't notice the cap. With a real model it decides how many calls you send at
once, which is how you stay under a provider's rate limit. The server uses `abatch()`, the async twin.

## Why not a plain `if` and a `for` loop?

`greet_with_if()` in `hello.py` gives exactly the same text, and a test checks that. The difference:

| | Plain `if` / `for` | `RunnableBranch` / `batch()` |
|---|---|---|
| The text | the same | the same |
| Runs a list | a `for` loop, one at a time | `.batch()`, several at a time, with a cap |
| Async, streaming | write it yourself | `.ainvoke()`, `.abatch()`, `.astream()` come with it |
| Fits in a chain | no: a function isn't a Runnable | yes: `branch \| next_step`, or a step inside a bigger chain |
| Tracing (later projects) | invisible | each step shows up in a LangSmith trace |

For one `if` in a script, the plain version is fine. Inside chains that call models, the Runnable version is what
the rest of LangChain plugs into.

## How a request flows

```text
one greeting:  POST /api/hello  {"name": "Raghu", "style": "formal"}
               HelloIn checks it → chain.ainvoke(...) → is_formal → formal_chain → {"answer": "Good day, Raghu. ..."}

a batch:       POST /api/batch  {"people": [{"name": "Raghu", "style": "formal"}, ... five people]}
               BatchIn checks every person → chain.abatch([...], max_concurrency=3) → {"answers": [five greetings]}
               a bad person → 422 with loc ["body", "people", 1, "style"]: the second person's style
```

## Run it

```bash
cd projects/07-langchain-branch
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python hello.py                    # both styles for Raghu, then a batch of five
python hello.py Asha formal        # Good day, Asha. Welcome to LangChain.
python -m pytest                   # 28 tests

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"name": "Raghu", "style": "formal"}'
curl -X POST http://127.0.0.1:8000/api/batch -H "Content-Type: application/json" \
     -d '{"people": [{"name": "Raghu", "style": "formal"}, {"name": "Asha", "style": "casual"}]}'
```

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Part A's next module is about how you build: an AI coding assistant writes a small data app while you review
every change.
