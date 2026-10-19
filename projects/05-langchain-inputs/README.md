# 05 · Pass several inputs

A chain with three inputs (a greeting, a name and a city), where `prompt.partial()` gives the greeting a default,
behind a server that checks every field and a page that shows each bad field's error next to it. Real prompts usually
have several inputs, some of them optional; this is how you fill them in and check them, still with no model and no
API key.

```text
{"greeting": "Good morning", "name": "Raghu", "city": "Dallas"}  ->  Good morning Raghu from Dallas, welcome to LangChain!
{"name": "Raghu", "city": "Dallas"}                              ->  Hello Raghu from Dallas, welcome to LangChain!
{"greeting": "Hi", "name": "", "city": "Dallas"}                 ->  422: one error for greeting, one for name
```

## What you'll build

- **`hello.py`**: the chain `prompt.partial(greeting="Hello") | to_text`. `python hello.py Asha Pune "Good morning"`
  prints `Good morning Asha from Pune, welcome to LangChain!`; leave the greeting off and it says Hello.
- **`main.py`**: a FastAPI server. `GET /` (or `/index.html`) serves the page; `POST /api/hello` takes a JSON body
  with `greeting` (optional), `name` and `city`, checks every field, and answers `{"answer": "..."}`, or a 422 that
  lists every bad field.
- **`index.html`**: a greeting list (its last choice, Hi, is refused on purpose), a name box and a city box. Each error
  the server reports appears in red next to its own field.

## What you'll learn

- **Several template variables**: `{greeting} {name} from {city}` in one template; `prompt.input_variables` lists all
  three, in alphabetical order.
- **`prompt.partial(greeting="Hello")`**: fills one variable in ahead of time and returns a new prompt, so that variable
  becomes optional; a greeting passed to `invoke()` still wins.
- **`Literal["Hello", "Good morning", "Namaste"] | None = None`**: a Pydantic field that accepts only these exact
  strings, and may be left out (or sent as `null`).
- **`body.model_dump(exclude_none=True)`**: the checked body as a plain dict, without the fields that are `None`; it
  goes straight into the chain.
- **Per-field 422 errors**: Pydantic checks every field and FastAPI reports all the bad ones in one 422; each error's
  `loc`, e.g. `["body", "city"]`, names its field.

## What's new since project 04

Compared with [Project 04 · Pass one input](../04-langchain-input/README.md):

- The template has three variables instead of one, and `prompt.partial()` gives the greeting a default.
- `HelloIn` has three fields instead of one: a `city` checked like `name`, and a `greeting` that is a `Literal[...]`
  and optional, the first optional field so far. The endpoint passes `body.model_dump(exclude_none=True)` to the chain
  instead of `{"name": body.name}`.
- The page has a `<select>` and a red error box for each field, and shows every entry of the 422's `detail` next to
  its field. Project 4 showed only the first entry, in the answer line.

## Before you start

- Python 3.11 or newer.
- No API key: nothing here calls a model.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt.partial(greeting="Hello") \| to_text`. Runs on its own: `python hello.py Asha Pune "Good morning"` |
| `main.py` | FastAPI: `GET /` (or `/index.html`) serves the page; `POST /api/hello` checks the body with `HelloIn` and runs the chain |
| `index.html` | The page: a greeting list, name and city boxes, and an error box next to each. Sends the fields as JSON |
| `tests/test_hello.py` | The tests: the variables, the partial, the script, the endpoint, each bad field and all of them at once, and the page |
| `pytest.ini` | Tells pytest to look in `tests/` and to import `hello` and `main` from this folder (`pythonpath = .`) |
| `requirements.txt` | The packages: `fastapi`, `uvicorn`, `langchain-core` (Pydantic comes with FastAPI) |
| `requirements-dev.txt` | `requirements.txt` plus `pytest` and `httpx`, for the tests |
| `README.md` | This page |

## How it works

### The template has three variables

`hello.py` starts with the template:

```python
# ① The template, with three slots. prompt.input_variables is ["city", "greeting", "name"]: LangChain lists the
#    variables in alphabetical order, not in the order they appear in the text.
prompt = PromptTemplate.from_template("{greeting} {name} from {city}, welcome to LangChain!")
```

The chain's input is a dict with one key per variable, in any order:
`{"greeting": "Namaste", "name": "Raghu", "city": "Dallas"}`.

### `partial()` gives the greeting a default

```python
# ② partial() fills one slot in ahead of time and gives back a new prompt; the original is unchanged.
#    Its input_variables is ["city", "name"]: greeting is no longer required, but a greeting passed in still wins.
prompt_with_default = prompt.partial(greeting="Hello")
...
# ④ Join them: the prompt with the default greeting first, then to_text.
chain = prompt_with_default | to_text
```

You can watch it work in a Python shell (`python` in this folder, with the venv active):

```pycon
>>> from hello import prompt, prompt_with_default, chain
>>> prompt_with_default.input_variables
['city', 'name']
>>> chain.invoke({"name": "Raghu", "city": "Dallas"})
'Hello Raghu from Dallas, welcome to LangChain!'
>>> chain.invoke({"greeting": "Namaste", "name": "Raghu", "city": "Dallas"})
'Namaste Raghu from Dallas, welcome to LangChain!'
>>> prompt.invoke({"name": "Raghu", "city": "Dallas"})
Traceback (most recent call last):
  ...
KeyError: "Input to PromptTemplate is missing variables {'greeting'}.  Expected: ['city', 'greeting', 'name'] ..."
```

`partial()` returns a new prompt; `prompt` itself still needs all three. A greeting passed to `invoke()` replaces the
default, so to get the default you leave the key out. That is what `python hello.py` does when you give it only a
name and a city:

```python
if __name__ == "__main__":
    ...
    inputs = {"name": name, "city": city}
    if len(sys.argv) > 3:
        inputs["greeting"] = sys.argv[3]
    print(chain.invoke(inputs))
```

### The page builds the body

The list in `index.html`:

```html
<select id="greeting">
  <option value="">(default: Hello)</option>
  <option>Hello</option>
  <option>Good morning</option>
  <option>Namaste</option>
  <option value="Hi">Hi (not allowed: see the 422)</option>
</select>
```

And what a submit sends:

```js
// Send name and city always; send greeting only when one is picked, so the prompt's default ("Hello") applies.
const body = { name: value("name"), city: value("city") };
if (value("greeting")) body.greeting = value("greeting");
```

- The first choice's value is the empty string, which counts as false in an `if`, so the greeting stays out of the
  body and the prompt's default applies.
- An `<option>` with no `value` sends its own text: picking Good morning sends `"Good morning"`.
- The last choice, "Hi (not allowed: see the 422)", sends `Hi` on purpose, so you can see the server refuse a greeting
  that isn't one of the three.
- As in project 4, the boxes have no `maxlength` or `required`, so the server's checks are what you see. A real app
  would check in both places: in the page for a quick hint, and on the server because anyone can send any request.

### FastAPI checks every field

`main.py` describes the body:

```python
class HelloIn(BaseModel):
    """The JSON body the page sends. FastAPI checks every field before hello() runs; each bad one gets its own error."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    greeting: Literal["Hello", "Good morning", "Namaste"] | None = None   # only these three; left out or null -> None
    name: str = Field(min_length=1, max_length=40)
    city: str = Field(min_length=1, max_length=40)
```

- **`Literal[...]`** accepts only these exact strings. Case and spaces count: `"namaste"` and `" Namaste "` are refused
  too, because the trimming only applies to the `str` fields.
- **`| None = None`** makes the field optional: when it is left out, or sent as `null`, it is `None`.
- **`Field(min_length=1, max_length=40)`** works as in project 4, now for both `name` and `city`.
- Pydantic checks every field instead of stopping at the first bad one, and FastAPI sends all the failures back in one
  422. Its `detail` has one entry per bad field, and `hello()` never runs.

The chain itself checks nothing: `python hello.py Asha Pune Hi` prints `Hi Asha from Pune, welcome to LangChain!`.
The three choices are `HelloIn`'s rule, so every request is checked when it reaches the server, before the chain runs.

### The chain runs with the body

```python
@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain with the fields from the request body and returns its answer."""
    # model_dump() turns the checked body into a dict: {"greeting": ..., "name": ..., "city": ...}. HelloIn's field
    # names are the template's variable names, so that dict is exactly the chain's input.
    # exclude_none=True leaves out a greeting that is None (not sent, or sent as null). Without it, None would
    # replace the partial's "Hello", and the answer would read "None Raghu from Dallas, ...".
    answer = await chain.ainvoke(body.model_dump(exclude_none=True))
    return {"answer": answer}
```

The two dicts, side by side, in a Python shell:

```pycon
>>> from main import HelloIn
>>> HelloIn(name="Raghu", city="Dallas").model_dump()
{'greeting': None, 'name': 'Raghu', 'city': 'Dallas'}
>>> HelloIn(name="Raghu", city="Dallas").model_dump(exclude_none=True)
{'name': 'Raghu', 'city': 'Dallas'}
```

The second one has no greeting, so the partial's Hello fills it in.

### The page puts each error next to its field

```js
if (res.status === 422) {
  // One entry per bad field. loc says which field: ["body", "name"] -> "name".
  const error = await res.json();
  const noBoxErrors = [];   // errors about a field this page has no box for, e.g. one you add to HelloIn
  error.detail.forEach((problem) => {
    const field = problem.loc.at(-1);
    const message = FRIENDLY[problem.type] ?? problem.msg;   // a type FRIENDLY doesn't list: the server's msg
    const box = errorBox(field);
    if (box) {
      box.textContent = message;
    } else {
      noBoxErrors.push(`${field}: ${message}`);
    }
  });
  answer.textContent = noBoxErrors.length > 0 ? noBoxErrors.join("; ") : "Please fix the fields marked in red.";
  return;
}
```

- `problem.loc.at(-1)` is the last item of `loc`: `["body", "name"]` gives `"name"`, and `errorBox("name")` is the red
  `<span id="name-error">` next to the name box.
- `FRIENDLY` turns the three error types this page's fields can get (`string_too_short`, `string_too_long` and
  `literal_error`) into plain words, shown in the table below. Any other type keeps the server's own `msg`.
- An error about a field the page has no box for goes into the answer line instead, as `field: message`, such as
  `age: Field required` (see Things to try).
- Any other failure, a 500 for example, shows `Something went wrong: the server answered HTTP 500`. Every submit
  first clears the old messages.

The whole trip:

```text
fill in the form, click   →  fetch("/api/hello", POST, {"greeting": "Good morning", "name": "Raghu", "city": "Dallas"})
                             (greeting is left out when the list says "(default: Hello)")
FastAPI                   →  reads the JSON into HelloIn and checks every field
   ├─ any bad field       →  422 {"detail": [one entry per bad field, each with loc ["body", "<field>"]]}
   │                         hello() never runs; the page writes each message next to its field
   └─ all good            →  hello(body)  →  await chain.ainvoke(body.model_dump(exclude_none=True))
JSON back                 →  {"answer": "Good morning Raghu from Dallas, welcome to LangChain!"} shown on the page
```

| You send | Server answers | The page shows |
|---|---|---|
| greeting `Good morning`, name `Raghu`, city `Dallas` | `200` `{"answer": "Good morning Raghu from Dallas, welcome to LangChain!"}` | Good morning Raghu from Dallas, welcome to LangChain! |
| no greeting, name `Raghu`, city `Dallas` | `200`, with the default greeting | Hello Raghu from Dallas, welcome to LangChain! |
| greeting `Hi` | `422`, greeting: `literal_error` | Pick Hello, Good morning or Namaste. (next to the list) |
| an empty (or spaces-only) name or city | `422`, that field: `string_too_short` | Please fill this in. (next to that box) |
| a name or city over 40 characters | `422`, that field: `string_too_long` | Too long: 40 characters at most. (next to that box) |
| several bad fields | `422`, one entry per bad field | each message next to its field |

For each of these 422s, the answer line under the button also says: Please fix the fields marked in red.

## Run it

```bash
cd projects/05-langchain-inputs
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

```bash
python hello.py                              # Hello Raghu from Dallas, welcome to LangChain!
python hello.py Asha Pune                    # Hello Asha from Pune, welcome to LangChain!
python hello.py Asha Pune "Good morning"     # Good morning Asha from Pune, welcome to LangChain!

uvicorn main:app --reload                    # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs → **POST /api/hello** → **Try it out** | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

The curl examples are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"greeting": "Namaste", "name": "Raghu", "city": "Dallas"}'
# {"answer":"Namaste Raghu from Dallas, welcome to LangChain!"}

curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"name": "Raghu", "city": "Dallas"}'
# {"answer":"Hello Raghu from Dallas, welcome to LangChain!"}

curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"greeting": "Hi", "name": "", "city": ""}'
# a 422 whose "detail" has three entries: literal_error for greeting, string_too_short for name and for city
```

## Test it

25 tests: 25 plain, 0 live (nothing here calls a model, so no key is needed). No server is started (FastAPI's
`TestClient` calls the app directly), and the page tests read `index.html` as text. They check:

- the template's three variables, and that `partial()` leaves the original prompt alone (2)
- the chain with the default greeting, and with a greeting passed in (2)
- `hello.py` run as a script four ways, including `Hi`, which the chain accepts (4)
- five good bodies: Good morning, Namaste, greeting left out, greeting `null`, spaces around name and city (5)
- six bodies with one bad field each, checking that only that field is reported, with the right `loc` and `type`:
  greeting Hi, greeting with spaces, empty name, only spaces in city, a 41-character city, no city at all (6)
- three bad fields in one request, all reported at once (1)
- `GET /api/hello` answers 405 (1)
- the page at `/` and at `/index.html`, with all three fields and their error boxes (2)
- that the page posts only on submit, and that it puts each error next to its field: its plain-word messages, the
  answer-line fallback and the "Something went wrong" line (2)

```bash
python -m pytest        # all 25
python -m pytest -v     # one line per test, with each case's name
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| The previous project's server is still running | The page at http://127.0.0.1:8000 still shows the previous project (its title says Project 4). On Windows, `uvicorn --reload` starts this server anyway, with no error, while the old one keeps answering. If uvicorn stops with an error about the address instead, it's the same problem | Press Ctrl+C in the old server's terminal, start this one again if it stopped, then reload the page |
| The venv isn't active, or the packages aren't installed | `ModuleNotFoundError: No module named 'langchain_core'` (or another package's name) | Activate `.venv` and run `pip install -r requirements-dev.txt` (see Run it) |
| You open `/api/hello` in the address bar | `{"detail":"Method Not Allowed"}` (405): the address bar sends a GET, and this route only takes POST | Use the page, `/docs`, or curl |
| You stop the server while the page is still open, then click the button | `Something went wrong:` followed by the browser's own reason | Start the server again: `uvicorn main:app --reload` |
| You paste the curl lines into Windows PowerShell | An error from PowerShell: there, `curl` is a different command (`Invoke-WebRequest`) | Use Git Bash, or `/docs` → **Try it out** |

## Things to try

1. **Drop `exclude_none=True`.** In `main.py`, change `body.model_dump(exclude_none=True)` to `body.model_dump()`. With
   "(default: Hello)" picked, the page now says `None Raghu from Dallas, welcome to LangChain!`, and `python -m pytest`
   gives 3 failed, 22 passed: the three requests with no greeting. Put it back.
2. **Add a fourth greeting.** Add `"Bonjour"` to the `Literal[...]` in `main.py` and `<option>Bonjour</option>` to the
   list in `index.html`, then reload the page (`--reload` restarts the server when `main.py` changes). Bonjour now
   works, all 25 tests still pass, and the server's 422 for Hi lists it:
   `Input should be 'Hello', 'Good morning', 'Namaste' or 'Bonjour'` (see it with curl or `/docs`). The page's red
   message for Hi still names only three greetings: that text is the page's own, in `FRIENDLY`, so it has to be
   changed by hand too. Change it, and `test_page_shows_each_error_next_to_its_field` fails until you give the test
   the same new text: it checks that line word for word.
3. **Add a field the page has no box for.** In `main.py`, add a line `age: int` under `city` in `HelloIn`. Every submit
   now ends with `age: Field required` in the answer line: the server's own message, because the page has no
   `age-error` box and `FRIENDLY` doesn't list the `missing` type. 12 tests fail while it's there; take it out again.

## Next

**[Project 06 · Run steps side by side](../06-langchain-parallel/README.md)**: back to one input, a name, and a chain
that splits: `RunnableParallel` runs three steps on the same greeting and returns their results as one dict.
