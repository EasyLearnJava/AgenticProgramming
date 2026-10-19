# 04 · Pass one input

The chain takes its first input: a name, typed into a box, sent to the server as JSON and checked by a Pydantic
model before it fills the template "Hello {name}, welcome to LangChain!". Projects 05-07 and 10-17 get their input
from the page the same way. No model, no API key.

```text
python hello.py Raghu                 ->  Hello Raghu, welcome to LangChain!
POST /api/hello  {"name": "Raghu"}    ->  200  {"answer": "Hello Raghu, welcome to LangChain!"}
POST /api/hello  {"name": ""}         ->  422  string_too_short   (the page says "Please type a name first.")
```

## What you'll build

- `hello.py`: a chain with a `{name}` slot. `python hello.py Raghu` prints "Hello Raghu, welcome to LangChain!";
  with no name it greets "World".
- `POST /api/hello` in `main.py`: it takes `{"name": "..."}`, trims the spaces around the name, checks that it is 1
  to 40 characters, and answers `{"answer": "..."}`, or a `422` that says what was wrong.
- A page with a name box and a button: a click or Enter sends the name, and the page shows the greeting, or the
  error in plain words ("Please type a name first.", "That name is too long: 40 characters at most.").

## What you'll learn

- **A template variable**: `{name}` is a slot in the template; `chain.invoke({"name": "Raghu"})` fills it, and
  leaving the key out raises a `KeyError`.
- **`sys.argv`**: how `python hello.py Raghu` hands the name to the script.
- **`POST` with a JSON body**: `fetch` with `method: "POST"`, a `Content-Type: application/json` header and
  `JSON.stringify({ name: ... })`.
- **A Pydantic model for the body**: `class HelloIn(BaseModel)` with `name: str = Field(min_length=1, max_length=40)`
  and `str_strip_whitespace=True`: the body's shape and rules in one place.
- **`422` validation**: FastAPI checks the body before `hello()` runs; the page reads `detail[0].type` and turns it
  into plain words.
- **A form's `submit` event**: one handler for a click on the button and for Enter in the box;
  `event.preventDefault()` keeps the page from reloading.

## What's new since project 03

[Project 03 · Run on a button click](../03-langchain-button/README.md) ran a chain with no input, once per button
click. Now:

- The template has a slot: `"Hello World, welcome to LangChain!"` becomes `"Hello {name}, welcome to LangChain!"`,
  so `chain.invoke({})` becomes `chain.invoke({"name": name})`, and `hello.py` reads the name from the command line.
- `GET /api/hello` becomes `POST /api/hello` with a JSON body, checked by a Pydantic model, `HelloIn`. A bad name
  gets a `422` and the chain never runs; a `GET` now gets `405 Method Not Allowed`.
- The page has a name box, and its button sits inside a `<form>`, handled on `submit` instead of `click`. A `422`
  is shown in plain words. The click counter is gone, and so is `cache: "no-store"`: a browser never answers a
  `POST` from its cache, so every submit reaches the server.

## Before you start

- Python 3.11 or newer (`python --version` shows yours).
- No model and no API key: the chain only fills in a template.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `PromptTemplate.from_template("Hello {name}, ...") \| to_text`. Run on its own, it greets the name you pass: `python hello.py Raghu` |
| `main.py` | FastAPI: `GET /` (or `/index.html`) serves the page; `POST /api/hello` checks the body with `HelloIn` and runs the chain |
| `index.html` | The page: a name box and a button inside a form. On submit (click or Enter) it POSTs the name as JSON and shows the answer or a plain-words error |
| `tests/test_hello.py` | The tests: the template variable, the chain, `hello.py` as a script, the endpoint and its 422s, and the page |
| `pytest.ini` | pytest's settings: put this folder on the import path (so the tests can `import hello` and `import main`) and look for tests only in `tests/` |
| `requirements.txt` | The packages the app needs: `fastapi`, `uvicorn`, `langchain-core` (Pydantic comes with FastAPI) |
| `requirements-dev.txt` | `requirements.txt` plus `pytest` (runs the tests) and `httpx` (FastAPI's `TestClient` needs it) |
| `README.md` | This guide |

## How it works

### The whole trip

```text
type "Raghu", click (or Enter)  →  fetch("/api/hello", POST, body {"name": "Raghu"})
FastAPI                         →  reads the JSON into HelloIn: trims spaces, checks 1-40 characters
   ├─ bad name                  →  422 {"detail": [{"type": "string_too_short", ...}]}   hello() never runs
   │                               the page shows "Please type a name first."
   └─ good name                 →  hello(body)  →  await chain.ainvoke({"name": "Raghu"})
JSON back                       →  {"answer": "Hello Raghu, welcome to LangChain!"} shown on the page
```

Steps 1 and 2 look at the chain itself (`hello.py`); steps 3 to 6 follow the trip, from the page to the server and
back.

### 1. The template has a slot (`hello.py` ① to ③)

```python
# ① The template: the text we want to show, with a {name} slot. prompt.input_variables is ["name"].
prompt = PromptTemplate.from_template("Hello {name}, welcome to LangChain!")
...
# ③ Join them: prompt first, then to_text. `a | b` is Python's a.pipe(b).
chain = prompt | to_text
```

`from_template` finds the `{name}` slot, so from now on the chain needs a dict with a `"name"` key every time it
runs. In a Python shell started in this folder:

```python
>>> from hello import chain, prompt
>>> prompt.input_variables
['name']
>>> chain.invoke({"name": "Raghu"})
'Hello Raghu, welcome to LangChain!'
>>> chain.invoke({})
Traceback (most recent call last):
  ...
KeyError: "Input to PromptTemplate is missing variables {'name'}.  Expected: ['name'] Received: [] ..."
```

The chain fills in whatever it is given and checks nothing: `chain.invoke({"name": ""})` gives
`'Hello , welcome to LangChain!'`. Checking the name is the server's job (steps 4 and 5).

### 2. Running `hello.py` on its own (④)

```python
if __name__ == "__main__":
    # sys.argv is the command line as a list: python hello.py Raghu -> ["hello.py", "Raghu"]. Item [0] is the
    # file's name, so the name you typed is [1]; with nothing after the file name, it's "World". Quote a name
    # with a space in it ("Raghu S"): unquoted, each word is its own item and only the first one is used.
    name = sys.argv[1] if len(sys.argv) > 1 else "World"
    answer = chain.invoke({"name": name})
    print(answer)
```

`a if test else b` is Python's form of `test ? a : b` in JavaScript or Java.

```text
python hello.py                       ->  Hello World, welcome to LangChain!
python hello.py Raghu                 ->  Hello Raghu, welcome to LangChain!
python hello.py Raghu Sanivarapu      ->  Hello Raghu, welcome to LangChain!   (only the first word)
python hello.py "Raghu Sanivarapu"    ->  Hello Raghu Sanivarapu, welcome to LangChain!
```

### 3. The page sends the name (`index.html`)

```html
  <form id="form">
    <label>Your name <input id="name" autocomplete="off"></label>
    <button id="run">Say hello</button>
  </form>
```

A `<button>` inside a `<form>` submits the form when you click it, and so does Enter in the name box. Both fire one
`submit` event, so one handler covers both:

```js
    form.addEventListener("submit", async (event) => {
      event.preventDefault();               // stay on this page: the form would otherwise reload it
      button.disabled = true;               // one request at a time
      answer.textContent = "Asking the server…";
      try {
        const res = await fetch("/api/hello", {
          method: "POST",
          headers: { "Content-Type": "application/json" },   // "the body is JSON": without it FastAPI answers 422
          body: JSON.stringify({ name: nameBox.value }),   // the JSON body: {"name": "..."}
        });
```

Project 03's `GET` only asked for an answer; this `POST` carries data. `JSON.stringify` turns the JavaScript object
into JSON text, and the header tells the server that the text is JSON. Leave the header out and `fetch` labels the
body `text/plain`, which FastAPI doesn't read as JSON ([Things to try](#things-to-try) 3).

The name box has no `maxlength` or `required` on purpose: the server does the checking, so you can see the 422.
A real app would check in both places: in the page for a quick hint, and on the server because anyone can send
any request.

### 4. FastAPI reads the body into `HelloIn` (`main.py`)

```python
class HelloIn(BaseModel):
    """The JSON body the page sends. FastAPI checks it before hello() runs; a bad one gets a 422."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)
```

A Pydantic model describes the body: one field, `name`, a string of 1 to 40 characters. `str_strip_whitespace=True`
trims the spaces first, so `"  Raghu  "` becomes `"Raghu"`, and a name of only spaces becomes `""`, which is too
short. Fields the model doesn't declare, such as a `"city"`, are ignored ([Things to try](#things-to-try) 4).

### 5. The route runs the chain, or FastAPI answers 422 first

```python
@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain with the name from the request body and returns its answer."""
    # body's type, HelloIn, is a Pydantic model, so FastAPI reads the JSON body into it (a plain `name: str`
    # would come from the address, ?name=...) and checks it first: a bad name gets a 422 and never gets here.
    # ainvoke() is invoke()'s async twin: the server can serve other requests while this one waits.
    answer = await chain.ainvoke({"name": body.name})
    return {"answer": answer}
```

The 422 for an empty name, exactly as the server sends it:

```json
{"detail":[{"type":"string_too_short","loc":["body","name"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
```

`detail` is a list with one entry per problem. `type` is a fixed code for the kind of problem, `loc` says where it
is (the body's `name`), and `msg` says it in English. A 41-character name gets `string_too_long`, and a body with no
`name` at all gets `missing`.

### 6. The page shows the answer, or the 422 in plain words (`index.html`)

```js
    // FastAPI's 422 says what was wrong in detail[0].type; turn the two we expect into plain words.
    const FRIENDLY = {
      string_too_short: "Please type a name first.",
      string_too_long: "That name is too long: 40 characters at most.",
    };
```

and, inside the submit handler, after the `fetch`:

```js
        if (res.status === 422) {
          const error = await res.json();
          // a ?? b is b when a is undefined (or null): an error type FRIENDLY doesn't list gets the server's msg.
          answer.textContent = FRIENDLY[error.detail[0].type] ?? `Not a valid name: ${error.detail[0].msg}`;
          return;
        }
        if (!res.ok) throw new Error(`the server answered HTTP ${res.status}`);   // any other error, e.g. a 500
        const data = await res.json();
        answer.textContent = data.answer;
```

`fetch` doesn't fail on a 422 or a 500: the server did answer. So the page handles the 422 itself; any other error
status is thrown and shown by the `catch`, e.g. `Something went wrong: the server answered HTTP 500`. As in
project 03, `finally` turns the button back on either way. The page reads only `detail[0]`: the name is the only field, so
there is one problem at most.

| You type | Server answers | The page shows |
|---|---|---|
| `Raghu` | `200` `{"answer": "Hello Raghu, welcome to LangChain!"}` | Hello Raghu, welcome to LangChain! |
| `  Raghu  ` | `200`, the spaces are trimmed | Hello Raghu, welcome to LangChain! |
| nothing, or only spaces | `422` `string_too_short` | Please type a name first. |
| 41 or more characters | `422` `string_too_long` | That name is too long: 40 characters at most. |

## Run it

```bash
cd projects/04-langchain-input
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then:

```bash
python hello.py                      # Hello World, welcome to LangChain!
python hello.py Raghu                # Hello Raghu, welcome to LangChain!
uvicorn main:app --reload            # the server: --reload restarts it when you save a .py file; Ctrl+C stops it
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 (or `/index.html`) | `https://<codespace-name>-8000.app.github.dev` (or `/index.html`) |
| Try the API by hand | http://127.0.0.1:8000/docs → **POST /api/hello** → **Try it out** | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

`/api/hello` only answers `POST`, so the address bar, which always sends a `GET`, gets a 405. Use the page, `/docs`,
or curl from a second terminal. These curl lines are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Raghu"}'
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": ""}'   # the 422
```

The first prints `{"answer":"Hello Raghu, welcome to LangChain!"}`; the second prints the 422 shown in step 5 of
How it works. In Windows PowerShell, `curl` is a different command; use this instead:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/hello -ContentType "application/json" -Body '{"name": "Raghu"}'
```

It prints the answer under an `answer` heading. For a bad name it stops with a red error that shows the server's
422 JSON, the same as in step 5 of How it works.

**Watch it.** In the browser, open DevTools (F12) → **Network**, submit a name, and click the `hello` request:
**Payload** shows the name the page sent, and **Response** shows the answer, or for an empty name the 422 with
`string_too_short`. The uvicorn terminal logs one line per request, ending in
`"POST /api/hello HTTP/1.1" 200 OK` or `"POST /api/hello HTTP/1.1" 422 Unprocessable Content`.

## Test it

```bash
python -m pytest        # all the tests: 17 passed
python -m pytest -v     # the same, one line per test, e.g. test_api_rejects_a_bad_name_with_422[only spaces]
```

17 tests: 17 plain, 0 live. There is no model here, so nothing needs a key, and no server is started either:
FastAPI's `TestClient` calls the app directly. They check:

- the prompt has exactly one variable, `name`, and the chain fills it in (2)
- the chain without the name raises `KeyError`; `pytest.raises` passes only if it does (1)
- `hello.py` as a script, with and without a name (2)
- `POST /api/hello` greets a name, a name with spaces around it, and a 40-character name (3)
- a `422` with the right error `type` for an empty name, only spaces, 41 characters, and no `name` field (4)
- `GET /api/hello` gets `405` (1)
- the page is served at `/` and `/index.html`, with the name box (2)
- the page's only `fetch` is inside the `submit` handler, which calls `event.preventDefault()` and sends `POST`,
  the `Content-Type` header and the name as JSON (1)
- the page has the plain words for both 422s, and the `Something went wrong` line for any other error (1)

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| You open `/api/hello` in the address bar | `{"detail":"Method Not Allowed"}` (405) | The address bar always sends a `GET`, and this route only accepts `POST`. Use the page, `/docs` or curl |
| You leave `-H "Content-Type: application/json"` out of a curl line | A 422 with `model_attributes_type`: "Input should be a valid dictionary or object to extract fields from" | Put the header back: it tells FastAPI that the body is JSON |
| You paste the curl lines into Windows PowerShell | `Cannot bind parameter 'Headers'...`: there `curl` means `Invoke-WebRequest` | Use Git Bash, `/docs`, or the `Invoke-RestMethod` line under the curl lines in Run it |
| Another project's server is still running | uvicorn stops with `error while attempting to bind on address ('127.0.0.1', 8000)` | Stop the other server (Ctrl+C in its terminal), then start this one |
| You stopped the server, or opened `index.html` straight from the folder, and then submitted | `Something went wrong: ` followed by your browser's own words for a failed request | Start `uvicorn main:app --reload` and open http://127.0.0.1:8000 |
| You renamed `{name}` in `hello.py` (say, to `{first_name}`) but not in `main.py` | The page: `Something went wrong: the server answered HTTP 500`. The terminal: `KeyError: "Input to PromptTemplate is missing variables {'first_name'}.  Expected: ['first_name'] Received: ['name'] ..."` | Use the same name in the template and in `chain.ainvoke({...})`. `python -m pytest` catches it too |

## Things to try

1. **Turn off the trimming.** In `main.py`, delete the `model_config = ConfigDict(str_strip_whitespace=True)` line
   and save (`--reload` restarts the server). Type only spaces and submit: instead of "Please type a name first.",
   the page greets the spaces: "Hello , welcome to LangChain!" (the browser shows a run of spaces as one; DevTools'
   **Response** shows them all). `python -m pytest` now reports 2 failures: `[spaces around it]` and `[only spaces]`.
2. **Change the limit in one place only.** In `main.py`, change `max_length=40` to `max_length=10`. Submit
   `Raghunathan` (11 letters): the server's 422 is still `string_too_long`, and its `ctx` now says
   `{"max_length":10}`, but the page still says "That name is too long: 40 characters at most.", because
   `index.html` has its own copy of the number. `python -m pytest` reports 1 failure: `[40 characters]`.
3. **Drop the JSON header.** In `index.html`, delete the `headers: { "Content-Type": "application/json" },` line
   and reload the page. Every submit now says "Not a valid name: Input should be a valid dictionary or object to
   extract fields from": without the header, `fetch` labels the body `text/plain;charset=UTF-8`, so FastAPI doesn't
   read it as JSON. `python -m pytest` reports 1 failure: `test_page_posts_the_name_as_json_only_on_submit`.
4. **Send a field the model doesn't know.** With the server running:

   ```bash
   curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Raghu", "city": "Dallas"}'
   ```

   You still get `{"answer":"Hello Raghu, welcome to LangChain!"}`: Pydantic ignores fields `HelloIn` doesn't
   declare, and the template has no `{city}` slot. The next project adds both.

## Next

**[Project 05 · Pass several inputs](../05-langchain-inputs/README.md)**: three inputs (a greeting, a name and a
city) in one template, a default greeting with `prompt.partial()`, and an error shown next to each bad field.
