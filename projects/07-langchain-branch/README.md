# 07 · Branch and batch a chain

This project builds a greeting chain that picks a formal or a casual path for each person, and runs on a whole list
of people in one call. Real apps need both moves, a different path for different inputs (`RunnableBranch`) and many
inputs at once (`batch()`), and here you learn them with no model and no API key.

```text
{"name": "Raghu", "style": "formal"}  ->  Good day, Raghu. Welcome to LangChain.
{"name": "Raghu", "style": "casual"}  ->  Hey Raghu! Welcome to LangChain!
a list of five people                 ->  five greetings, in the same order, at most 3 running at a time
```

## What you'll build

- `hello.py`: two greeting chains, formal and casual, and a `RunnableBranch` that runs one of them for each input.
  `python hello.py Asha` greets Asha in both styles, then greets five people with one `batch()` call.
- `main.py`: a FastAPI server. `POST /api/hello` greets one person; `POST /api/batch` greets 1 to 10 people in one
  call and gives back their greetings in the same order. It also serves the page at `/`.
- `index.html`: a page with two forms: a name with a formal/casual choice, and a box of `name,style` lines greeted as
  one batch. If one person is wrong, it says which: `Person 2, style: must be formal or casual`.

## What you'll learn

- **`RunnableBranch((condition, path), ..., default)`**: the conditions are checked in order, the first one that is
  true picks the one path that runs, and the default runs when none is.
- **A plain function as the condition**: `is_formal(inputs) -> bool` gets the whole input, and `RunnableBranch` wraps
  it in a `RunnableLambda` for you.
- **`batch()` and `abatch()`**: a list of inputs in, a list of answers out in the same order, with several running at
  once.
- **`config={"max_concurrency": 3}`**: `config` holds the settings for one run (a `RunnableConfig`), and
  `max_concurrency` caps how many inputs run at once. It only works inside `config`.
- **A list in a Pydantic model**: `people: list[HelloIn]` with 1 to 10 items, and a 422 that names the bad person and
  field: `["body", "people", 1, "style"]`.
- **What a Runnable adds over a plain `if` and a `for` loop**: the same text, plus batching, async and a place in a
  bigger chain.

## What's new since project 06

- [Project 06 · Run steps side by side](../06-langchain-parallel/README.md) ran every step on the same input. Here
  `RunnableBranch` runs exactly one of two paths, picked for each input by `is_formal()`.
- `batch()` and `abatch()` run the chain on a whole list in one call, capped with `config={"max_concurrency": 3}`:
  the first time this repo passes a `config`.
- A new endpoint, `POST /api/batch`, takes a list of the same `HelloIn` model, and its 422 says which person is wrong.
  06's `GET /api/graph` and the graph on the page are gone.
- The page has two forms, and both send their request through one `post()` helper.

## Before you start

- Python 3.11 or newer.
- No API key: nothing in this project calls a model.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: two paths, the condition `is_formal()`, the branch, and `greet_with_if()` (the same without LangChain). Run on its own, it greets one name in both styles, then a batch of five |
| `main.py` | The FastAPI server: `GET /` and `/index.html` serve the page, `POST /api/hello` runs the chain once, `POST /api/batch` runs it on a list with `abatch()` |
| `index.html` | The page: a name with a formal/casual choice, and a box of `name,style` lines sent as one batch |
| `tests/test_hello.py` | The tests for the chain, the script, both endpoints and the page |
| `pytest.ini` | Tells pytest to look for tests in `tests/` and to import `hello` and `main` from this folder |
| `requirements.txt` | The packages the project needs: `fastapi`, `uvicorn`, `langchain-core` |
| `requirements-dev.txt` | `requirements.txt` plus `pytest` and `httpx`, for the tests |
| `README.md` | This guide |

## How it works

### The two paths

```python
# ① The converter, shared by both paths: the prompt gives back a StringPromptValue, this turns it into text.
to_text = RunnableLambda(lambda value: value.to_string(), name="to_text")

# ② Two paths: the same idea as before, one chain per style.
formal_chain = PromptTemplate.from_template("Good day, {name}. Welcome to LangChain.") | to_text
casual_chain = PromptTemplate.from_template("Hey {name}! Welcome to LangChain!") | to_text
```

Each path is an ordinary `prompt | to_text` chain, like the ones in earlier projects, and runs on its own:
`formal_chain.invoke({"name": "Raghu"})` gives `"Good day, Raghu. Welcome to LangChain."`.

### The condition

```python
# ③ The condition: gets the whole input and says True or False.
#    It's a plain function, not a Runnable: RunnableBranch wraps it in a RunnableLambda for you.
def is_formal(inputs: dict) -> bool:
    return inputs["style"] == "formal"
```

It gets the whole input, `{"name": "Raghu", "style": "formal"}`, not just the style. The wrapping is the same kind of
help LangChain gives a plain dict in a chain, which it turns into a `RunnableParallel` (project 6).

### The branch

```python
# ④ The branch: (condition, path) pairs, checked in order; the first true one picks the path.
#    The last argument, on its own, is the default: used when no condition is true.
chain = RunnableBranch(
    (is_formal, formal_chain),
    casual_chain,
)
```

The branch gives the whole input to each condition in turn and runs the first path whose condition says `True`. That
path gets the same whole input; its template uses only `{name}`. Only the chosen path runs, where project 6's
`RunnableParallel` ran all of its steps.

Any style other than exactly `"formal"` takes the default path: `chain.invoke({"name": "Raghu", "style": "loud"})`
says "Hey Raghu!", and so does `"Formal"`, because `==` is exact. The server is stricter: it lets only `"formal"` and
`"casual"` through (see [The server](#the-server)).

More paths are more pairs, checked in order:
`RunnableBranch((is_formal, formal_chain), (is_pirate, pirate_chain), casual_chain)`.

The path is picked only when the chain runs, so `chain.get_graph()` (project 6) draws a single `Branch` step, not the
two paths.

### The script and the batch

```python
# ⑥ Run it, but only when this file is run directly (python hello.py), not when main.py imports it.
#    The first argument is the name. A second one is the style: then only that one greeting is printed.
if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    if len(sys.argv) > 2:
        print(chain.invoke({"name": name, "style": sys.argv[2]}))
    else:
        print(chain.invoke({"name": name, "style": "formal"}))
        print(chain.invoke({"name": name, "style": "casual"}))
        print()
        # batch(): a list in, a list out, in the same order. config= holds settings for the run: with
        # "max_concurrency": 3, at most 3 run at the same time. It only works inside config=: in
        # chain.batch(people, max_concurrency=3) it is passed on to each invoke() instead, and nothing is capped.
        people = [
            {"name": "Raghu", "style": "formal"},
            {"name": "Asha", "style": "casual"},
            ...
        ]
        for answer in chain.batch(people, config={"max_concurrency": 3}):
            print(answer)
```

`python hello.py Asha` prints Asha in both styles, a blank line, then the batch:

```text
Good day, Asha. Welcome to LangChain.
Hey Asha! Welcome to LangChain!

Good day, Raghu. Welcome to LangChain.
Hey Asha! Welcome to LangChain!
Good day, Ken. Welcome to LangChain.
Hey Mia! Welcome to LangChain!
Hey Li! Welcome to LangChain!
```

`batch()` takes a list of inputs and gives back a list of answers in the same order. Each input goes through the
branch on its own, so one batch can mix styles. `batch()` runs the inputs on a pool of threads, and `abatch()`, its
async twin (the server uses it), runs them concurrently with asyncio. Either way, `max_concurrency` decides how many
run at once; a test checks that eight slow inputs with a cap of 3 never have more than three running.

`config` is the second argument of every way to run a Runnable (`invoke`, `batch`, `stream` and their async twins): a
dict of settings for that run, LangChain's `RunnableConfig`. `max_concurrency` is one of its keys, and it only works
there. `chain.batch(people, max_concurrency=3)` passes the keyword on to each `invoke()` instead: on this chain nothing
is capped and nothing complains, and on a `RunnableLambda` it is a `TypeError`.

With instant steps like these you won't notice the cap. With a real model it caps how many calls are running at once,
so a list of 100 doesn't send 100 requests together. It doesn't limit calls per minute, which is what a provider's
rate limit usually counts, so the cap helps but doesn't guarantee you stay under it. Project 14 batches real Gemini
calls this way.

### Branch and batch vs a plain `if` and a `for` loop

```python
def greet_with_if(inputs: dict) -> str:
    if inputs["style"] == "formal":
        return f"Good day, {inputs['name']}. Welcome to LangChain."
    return f"Hey {inputs['name']}! Welcome to LangChain!"
```

`greet_with_if()` in `hello.py` gives exactly the same text, and a test checks that for all five people. The
difference:

| | Plain `if` / `for` | `RunnableBranch` / `batch()` |
|---|---|---|
| The text | the same | the same |
| Runs a list | a `for` loop, one at a time | `.batch()`, several at a time, with a cap |
| Async, streaming | write it yourself | `.ainvoke()`, `.abatch()`, `.astream()` come with it |
| Fits in a chain | only wrapped: next to a Runnable, `\|` turns the function into one `RunnableLambda` step, with the whole `if` inside it | yes: `branch \| next_step`, and each path is a chain you can run and test on its own |
| Tracing (LangSmith, a later project) | one step at most: the function | every step: the branch, the condition, the chosen path and its steps |

For one `if` in a script, the plain version is fine. Inside chains that call models, the Runnable version is what the
rest of LangChain plugs into.

### The server

```python
class HelloIn(BaseModel):
    """One person: a name and the style to greet them in. The style decides which branch runs."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)
    style: Literal["formal", "casual"]   # must match exactly: not stripped, so " formal " is a 422


class BatchIn(BaseModel):
    """A list of people, greeted in one call. Capped at 10 so one request can't ask for thousands."""
    people: list[HelloIn] = Field(min_length=1, max_length=10)
```

`HelloIn` makes the server stricter than the chain: `"loud"` gets a 422 (`literal_error`) before the chain runs,
though the chain itself would take the default path. `BatchIn` is a list of the same model, 1 to 10 people. FastAPI
checks every person before anything runs, so one bad person rejects the whole batch, and the 422's `loc` says which:
`["body", "people", 1, "style"]` is the second person's style (the list counts from 0).

```python
@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain once. The branch inside picks the formal or the casual path from body.style."""
    answer = await chain.ainvoke(body.model_dump())
    return {"answer": answer}


@app.post("/api/batch")
async def batch(body: BatchIn):
    """Runs the chain on every person in one call, at most 3 at a time. The answers keep the list's order."""
    # abatch() is batch()'s async twin.
    answers = await chain.abatch([person.model_dump() for person in body.people], config={"max_concurrency": 3})
    return {"answers": answers}
```

`model_dump()` turns a checked model back into the plain dict the chain takes, `{"name": "Raghu", "style": "formal"}`.
A request flows like this:

```text
one greeting:  POST /api/hello  {"name": "Raghu", "style": "formal"}
               HelloIn checks it → chain.ainvoke(...) → is_formal → formal_chain → {"answer": "Good day, Raghu. ..."}

a batch:       POST /api/batch  {"people": [{"name": "Raghu", "style": "formal"}, ... five people]}
               BatchIn checks every person → chain.abatch([...], config={"max_concurrency": 3})
               → {"answers": [five greetings]}
               a bad person → 422 with loc ["body", "people", 1, "style"], and nobody is greeted
```

### The page

Both forms send their JSON through one helper:

```js
async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok && res.status !== 422) throw new Error(`the server answered HTTP ${res.status}`);   // e.g. a 500
  return [res.status, await res.json()];
}
```

A 200 (the answer) and a 422 (what was wrong) both come back to the form. Any other status is thrown, and the form
shows `Something went wrong: the server answered HTTP 500` (or, if the server can't be reached at all, the browser's
own reason).

The batch form turns the box into the list, one person per non-blank line:

```js
const people = document.getElementById("people").value
  .split("\n")
  .filter((line) => line.trim())
  .map((line) => {
    const [name, style = ""] = line.split(",");
    // The server trims the name, but the style must be exactly "formal" or "casual", so trim it here
    // ("Raghu, formal" sends " formal" otherwise, and that's a 422).
    return { name, style: style.trim() };
  });
```

A 422 is shown in plain words: `explain()` looks up each problem's `type` in `FRIENDLY` (`literal_error` becomes
"must be formal or casual") and falls back to the server's own `msg`. The batch form also says which person and field,
from `loc`, counting people, not lines: blank lines were skipped, so `Person 3` is the third person in the box.

## Run it

```bash
cd projects/07-langchain-branch
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

```bash
python hello.py                      # Raghu in both styles, then a batch of five
python hello.py Asha                 # Asha in both styles, then the same batch
python hello.py Asha formal          # Good day, Asha. Welcome to LangChain.

uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

To call the API from a terminal instead (these curl examples are for bash: macOS, Linux, Codespaces, Git Bash):

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"name": "Raghu", "style": "formal"}'
# {"answer":"Good day, Raghu. Welcome to LangChain."}

curl -X POST http://127.0.0.1:8000/api/batch -H "Content-Type: application/json" \
     -d '{"people": [{"name": "Raghu", "style": "formal"}, {"name": "Asha", "style": "casual"}]}'
# {"answers":["Good day, Raghu. Welcome to LangChain.","Hey Asha! Welcome to LangChain!"]}
```

## Test it

The tests need no server and no network: FastAPI's `TestClient` sends their requests straight to the app. They check:

- the condition and each path on their own; the branch for `formal`, `casual` and `loud` (the default path); and that
  `greet_with_if()` gives the same text as the branch for all five people
- that `batch()` keeps the order, and that `max_concurrency` really caps a slow stand-in step at 3 running at once
- `hello.py` run with no arguments, with a name, and with a name and a style
- `POST /api/hello` in both styles, and its 422s: an unknown style, a style with spaces around it, no style, and an
  empty, blank or 41-character name
- `POST /api/batch` with five people, its 1-to-10 limits, and the `loc` that names the bad person
- that the API routes don't answer `GET`, and that the page is served, sends each request only from a submit handler,
  and shows errors as described above

33 tests: 33 plain, 0 live (nothing here calls a model).

```bash
python -m pytest                     # all 33 tests
python -m pytest -k batch            # only the tests with "batch" in their name: 6 of them
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| The script gets a style the branch doesn't know: `python hello.py Asha Formal` | `Hey Asha! Welcome to LangChain!`, and no error | The condition is an exact `== "formal"`, so anything else takes the default path. Type `formal` in lower case |
| One line in the batch box is wrong, e.g. `Asha,Formal` on the second line | No greetings at all, only `Person 2, style: must be formal or casual` | The server checks the whole list before the chain runs, so one bad person stops the batch. Fix that line |
| `max_concurrency` passed as a keyword: `chain.batch(people, max_concurrency=3)` | No error and no cap on this chain; on a `RunnableLambda`, `TypeError: ... got an unexpected keyword argument 'max_concurrency'` | Put it inside `config`: `chain.batch(people, config={"max_concurrency": 3})` |
| The previous project's server is still running when you start this one | On Windows, with `--reload`: no error, yet http://127.0.0.1:8000 can still show the previous project's page: `uvicorn` says it is running, but the old server goes on answering. If the old one runs without `--reload`, the new one stops with `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`. Other systems may show an error instead | Stop the old server (Ctrl+C in its terminal) and reload the page, or run this one on another port with `uvicorn main:app --reload --port 8001` and open http://127.0.0.1:8001 instead |

## Things to try

1. **A style the branch doesn't know.** Run `python hello.py Asha loud` and `python hello.py Asha Formal`: both print
   `Hey Asha! Welcome to LangChain!`, the default path. Send the same to the server and it answers 422 instead:

   ```bash
   curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
        -d '{"name": "Asha", "style": "loud"}'
   ```

   The answer is a `literal_error` with `"msg":"Input should be 'formal' or 'casual'"`.

2. **A third path.** In `hello.py`, add a pirate path under the other two:

   ```python
   pirate_chain = PromptTemplate.from_template("Ahoy {name}! Welcome aboard LangChain!") | to_text
   ```

   add its condition under `is_formal`:

   ```python
   def is_pirate(inputs: dict) -> bool:
       return inputs["style"] == "pirate"
   ```

   and add `(is_pirate, pirate_chain),` to the branch, before `casual_chain`. `python hello.py Asha pirate` prints
   `Ahoy Asha! Welcome aboard LangChain!`, and `python -m pytest` still passes. The server keeps answering 422 for
   `"pirate"` until you add it to `HelloIn`: `style: Literal["formal", "casual", "pirate"]`.

3. **See the graph.** Run `python -c "from hello import chain; print(chain.get_graph().draw_mermaid())"`. After a short
   `---` config header, the graph has just three nodes, `PromptInput`, `Branch` and `BranchOutput`, and two arrows:
   `PromptInput --> Branch;` and `Branch --> BranchOutput;`. The paths aren't drawn, because the branch picks one only
   when it runs.

4. **Watch the cap.** In `tests/test_hello.py`, in `test_max_concurrency_caps_how_many_run_at_once`, change
   `"max_concurrency": 3` to `1` and run `python -m pytest -k max_concurrency`. It fails with `assert 1 == 3`: one at a
   time. Put it back.

## Next

**[Project 08 · Vibe-code a data app](../08-vibecode-data-app/README.md)**: an AI coding assistant writes a small
Streamlit app over a CSV of fruit sales, one mini-spec at a time, while you review every change.
