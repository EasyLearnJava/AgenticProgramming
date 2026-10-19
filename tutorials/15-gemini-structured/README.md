# 15 · Structured output

Gemini returns **typed data** instead of free text: a Pydantic object with every field filled in and checked, so
code can use it straight away. Two examples: a greeting with four fields, and a messy support message turned into
a ticket that says which team should handle it.

```text
greet  {"name": "Asha", "language": "Hindi"}
   ->  {"message": "नमस्ते आशा! LangChain में आपका स्वागत है।", "language": "Hindi", "emoji": "🙏", "tone": "warm"}

triage {"message": "hi, i ordered the blue jacket last week and you took the money TWICE from my card!!! ..."}
   ->  {"intent": "Refund a double charge", "category": "billing", "urgency": "high", "route_to_team": "billing_team"}
       (made-up examples: Gemini's words change every time)
```

## What you'll build

- **`hello.py`**: two Pydantic classes, `Greeting` (message, language, emoji, tone) and `Ticket` (intent, category,
  urgency, route_to_team), and a chain for each, built with `with_structured_output`. `python hello.py` prints one
  greeting and one ticket, field by field, then which team gets the ticket first when its urgency is high.
- **`main.py`**: `POST /api/greet` and `POST /api/triage` return those objects as JSON, and `/docs` shows both
  shapes. `GET /api/setup` gives the page its list of languages and a sample message.
- **`index.html`**: a name-and-language form, and a box that already holds a messy support message. Each field of
  the answer appears in its own box.

## What you'll learn

- **`model.with_structured_output(Greeting)`**: the chain returns a `Greeting` object, not a string
- **A Pydantic class as the model's schema**: field types, `Literal` choices and `Field(description=...)` become the
  JSON schema Gemini receives
- **Gemini's native structured output** (`method="json_schema"`, the default): the request carries
  `response_mime_type="application/json"` and that schema
- **Types are checked, descriptions only guide**: a reply with a missing field or a choice that isn't allowed raises
  `OutputParserException`, which the server turns into a 502
- **Messy text into data code can act on**: `if ticket.urgency == "high": ...`
- **`response_model=` on a FastAPI route**: `/docs` shows the exact shape of the answer

## What's new since project 14

- [Project 14 · Show, don't tell: few-shot examples](../14-gemini-few-shot/README.md) showed the format with
  examples and checked each answer in code with `follows_format()`. Here the format is a Pydantic class sent with
  the request, and `with_structured_output(...)` takes the place of `| model | StrOutputParser()`: the chain returns
  a checked object, not text.
- The prompts don't show or describe the format any more: no examples, no "answer in JSON". The schema carries it.
- Pydantic now checks what comes **back** from the model, with the same `BaseModel`, `Field` and `Literal` that
  have checked request bodies since projects 4 and 5. `response_model=` (new) puts that shape in `/docs`.
- One call per request again (no `RunnableParallel` or `abatch`), so any failure, a refused answer included, is a
  502. The page builds one box per field with `Object.entries` (new).

## Before you start

- Python 3.11 or newer.
- Your Gemini key from [project 9](../09-gemini-key/README.md), copied into this folder once:

  ```bash
  cd tutorials/15-gemini-structured
  cp ../09-gemini-key/.env .env
  ```

  In GitHub Codespaces you can use a Codespaces secret named `GOOGLE_API_KEY` instead.

## Files

| File | What it is |
|---|---|
| `hello.py` | The two classes, `Greeting` and `Ticket`; the two prompts; and the two chains, `greet_chain` and `triage_chain`. `python hello.py` prints one of each, field by field |
| `main.py` | FastAPI: `POST /api/greet` and `POST /api/triage` return the objects as JSON, and `response_model` puts their shape in `/docs`; `GET /api/setup` gives the page its dropdown and sample message |
| `index.html` | The page: the two forms, and each field of the answer in its own box |
| `config.py` | Loads and checks the key: the same file as project 9 |
| `.env.example` | What `.env` looks like (`GOOGLE_API_KEY=your-key-here`). Your real `.env` is in `.gitignore`, so it stays out of git |
| `tests/test_hello.py` | The tests: plain ones that make no model call, and live ones that call Gemini |
| `tests/conftest.py` | Skips the live tests when there is no key |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, only looks in `tests/`, and defines the `live` marker |
| `requirements.txt` | The packages the app needs: the same as project 10 |
| `requirements-dev.txt` | `requirements.txt` plus pytest and httpx, for the tests |
| `README.md` | This file |

## How it works

### The shapes you want back

```python
Language = Literal["English", "Hindi", "Telugu", "Tamil", "Spanish", "French"]
LANGUAGES = list(get_args(Language))          # get_args() lists a Literal's choices: ["English", "Hindi", ...]


# ① The shapes we want back. Each field has a type, and can have a description that Gemini reads as an instruction.
#    Literal["warm", "playful", "formal"] means: one of these three, and nothing else.
class Greeting(BaseModel):
    """A short welcome for someone starting to learn LangChain."""
    message: str = Field(description="The welcome itself, one or two sentences, written in the requested language")
    language: Language = Field(description="The language the message is written in")
    emoji: str = Field(description="One emoji that fits the message")
    tone: Literal["warm", "playful", "formal"] = Field(description="How the message sounds")
```

Each part tells Gemini something, but only some of it is checked when the answer comes back:

| Part | Tells Gemini | Checked by Pydantic? |
|---|---|---|
| The field names and types | Which keys to fill in, and what kind of value goes in each | Yes: a missing field or a wrong type is refused |
| `Literal["warm", "playful", "formal"]` | One of these, and nothing else | Yes: `"tone": "angry"` is refused |
| `Field(description=...)` | What the field is for: it reads like an instruction | No: nothing counts the sentences |
| The class docstring | What the whole object is | No |

`Language` is written once and used three times: in `Greeting` (what Gemini may answer), in `main.py`'s request
model (what the page may send, so `"Klingon"` gets a 422 before any call), and for the page's dropdown, through
`LANGUAGES`.

Pydantic does the same job here as for FastAPI's request bodies since project 4, but the other way round: there it
checked what **the page** sent, and here it checks what **Gemini** sends back.

### The prompts don't describe the format

```python
# ② The prompts: ordinary chat prompts. They don't describe the format: the schema does that.
greet_prompt = ChatPromptTemplate.from_messages([
    ("system", "You write short, friendly welcomes for people who are starting to learn LangChain."),
    ("human", "Write a welcome for {name}, in {language}."),
])
```

No "answer in JSON with these keys": the schema already says that, exactly. The prompt only says what to write.
Compare it with project 14, where the format had to be shown with examples and checked with `follows_format()`.

### What `with_structured_output` adds: a bound model and a parser

```python
greet_chain = greet_prompt | model.with_structured_output(Greeting)
triage_chain = triage_prompt | model.with_structured_output(Ticket)
```

`with_structured_output(Greeting)` adds two steps after the prompt, and a test checks both:

1. **The model, told to answer in JSON of that shape.** Two settings are bound to it (`bind()`, as in
   [project 11](../11-gemini-tokens/README.md)): `response_mime_type="application/json"`, and
   `response_json_schema`, the JSON schema made from the class (`Greeting.model_json_schema()`). Both go with the
   request, so Gemini writes its answer to fit the schema. This is Gemini's native structured output, called
   `method="json_schema"` in langchain-google-genai, and it's the default.
2. **A parser**, `PydanticOutputParser`, which reads the JSON and builds a `Greeting` from it. If anything doesn't
   fit, like a missing field or `"tone": "angry"`, it raises `OutputParserException` instead of handing you bad data.

You could build the same two steps yourself. This is what `with_structured_output` makes, apart from a label that
only tracing tools such as LangSmith read:

```python
from langchain_core.output_parsers import PydanticOutputParser

by_hand = (
    model.bind(response_mime_type="application/json", response_json_schema=Greeting.model_json_schema())
    | PydanticOutputParser(pydantic_object=Greeting)
)
```

This is what Gemini receives for one of the ticket's fields: its choices, and its description as an instruction.

```text
    "urgency": {
      "description": "high: money lost, or the customer can't use the product at all; medium: ...",
      "enum": [
        "low",
        "medium",
        "high"
      ],
      "title": "Urgency",
      "type": "string"
    },
```

So there's no `StrOutputParser` and no text to search through: the chain gives you the object, and the main block
prints it field by field:

```python
    greeting = greet_chain.invoke({"name": "Asha", "language": "Hindi"})
    print(f"greet_chain returned a {type(greeting).__name__} object, not a str:")
    for field, value in greeting.model_dump().items():     # model_dump(): the object's fields, as a dict
        print(f"  {field:>13}: {value}")                   # :>13 right-aligns each name, so the colons line up
```

### Messy text into a ticket

```python
class Ticket(BaseModel):
    """A customer support message, sorted so the right team can act on it."""
    intent: str = Field(description="What the customer wants, in at most ten words")
    category: Literal["billing", "technical", "account", "shipping", "other"]
    urgency: Literal["low", "medium", "high"] = Field(
        description="high: money lost, or the customer can't use the product at all; "
                    "medium: something is broken or late; low: a question or a request"
    )
    route_to_team: Literal["billing_team", "support_engineers", "account_team", "logistics", "general_support"]
```

`SAMPLE_MESSAGE` is in lower case, with typos, shouting, and two problems at once (a double charge and a late
jacket). Apart from `intent`, the ticket that comes back has only fixed choices, so code can act on it without
reading the text. The end of `hello.py`'s main block does exactly that:

```python
    # Code can act on the fields straight away: no searching through text.
    if ticket.urgency == "high":
        print(f"\n-> {ticket.route_to_team} gets this first: {ticket.intent}")
```

The `urgency` description gives the rule for each level. Without it, "high" would be left to Gemini's own judgement.
`category` and `route_to_team` have no description: their names and their choices are all Gemini has to go on.

### The server and the page

`main.py` checks each request with its own Pydantic model before anything else runs. `GreetIn` reuses `Language`:

```python
class GreetIn(BaseModel):
    ...
    name: str = Field(min_length=1, max_length=40)
    language: Language                  # the same Literal as Greeting.language: "Klingon" gets a 422, before any call
```

Then the route runs the chain through `run()`, which turns any failure into a 502:

```python
async def run(chain, inputs):
    """Runs a chain; any failure, including an answer that doesn't fit the schema, becomes a 502."""
    try:
        return await chain.ainvoke(inputs)
    except Exception as err:
        # The full reason goes to the server's terminal; the page only learns the error's type.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err


# response_model=Greeting: /docs shows the answer's exact shape, taken from the Greeting class.
# (FastAPI would send the returned object as the same JSON without it.)
@app.post("/api/greet", response_model=Greeting)
async def greet(body: GreetIn):
    """One welcome, as a Greeting object: one real call to Gemini."""
    return await run(greet_chain, body.model_dump())      # {"name": "Asha", "language": "Hindi"}: the prompt's inputs
```

The route returns the `Greeting` object itself, and FastAPI sends it as JSON. On the page, `showFields()` makes one
box per key of that JSON, so a new field in `Greeting` would show up as a new box with no change to the page:

```js
    // One box per field: its name on top, its value below.
    function showFields(id, data) {
      const boxes = Object.entries(data).map(([name, value]) => {
        ...
      });
      document.getElementById(id).replaceChildren(...boxes);
    }
```

`Object.entries(data)` turns `{"message": "...", "tone": "warm", ...}` into `[["message", "..."], ["tone", "warm"],
...]`: one `[name, value]` pair per field.

## Run it

From the repository's top folder (skip the `cd` if you're already in this folder):

```bash
cd tutorials/15-gemini-structured
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the key copied as in [Before you start](#before-you-start):

```bash
python config.py                     # GOOGLE_API_KEY is set.
python hello.py                      # one greeting and one ticket, field by field (two real calls)
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

In Git Bash on Windows, run `export PYTHONUTF8=1` first, or `python hello.py` stops at the Hindi greeting:
[When things go wrong](#when-things-go-wrong) says why.

`python hello.py` prints something like this (made-up example: Gemini's words change every time):

```text
greet_chain returned a Greeting object, not a str:
        message: नमस्ते आशा! LangChain सीखने की आपकी यात्रा में आपका स्वागत है।
       language: Hindi
          emoji: 🙏
           tone: warm

triage_chain returned a Ticket object:
         intent: Refund a double charge and find the missing jacket
       category: billing
        urgency: high
  route_to_team: billing_team

-> billing_team gets this first: Refund a double charge and find the missing jacket
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

`/docs` shows the exact shape of each answer, taken from the same `Greeting` and `Ticket` classes.

You can also call the API with curl. These commands are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl http://127.0.0.1:8000/api/setup
curl -X POST http://127.0.0.1:8000/api/greet -H "Content-Type: application/json" \
     -d '{"name": "Asha", "language": "Hindi"}'
curl -X POST http://127.0.0.1:8000/api/triage -H "Content-Type: application/json" \
     -d '{"message": "my app keeps crashing when i log in, i cant use it at all"}'
curl -X POST http://127.0.0.1:8000/api/greet -H "Content-Type: application/json" \
     -d '{"name": "Asha", "language": "Klingon"}'     # a 422: not one of the languages, and no call to Gemini
```

## Test it

The plain tests make no model call: the chains are swapped for stand-ins, or only the parser runs. The live tests
call Gemini, and `tests/conftest.py` skips them when there is no key.

- **The schemas (7 tests)**: `Greeting`'s schema lists every field as required; both schemas carry their `Literal`
  choices and the descriptions Gemini reads, the urgency rule included. Pydantic accepts good data, and refuses
  `"tone": "angry"`, `"language": "Klingon"`, an emoji of `None`, and a ticket with no urgency.
- **The model and the chains (6 tests)**: the model is `gemini-3.5-flash-lite` with a cap of 300 output tokens;
  each chain is prompt, then model, then `PydanticOutputParser`; the model step carries
  `response_mime_type="application/json"` and exactly `Greeting.model_json_schema()`; the parser turns JSON into a
  `Greeting`, and refuses `"tone": "angry"` with `OutputParserException`; with no key, `hello.py` stops with the
  message, not a traceback.
- **The endpoints and the page (10 tests)**: `/api/setup` gives the languages and the sample message;
  `/api/greet` and `/api/triage` return every field, and the spaces around a name are trimmed; three bad inputs get
  a 422 and no model call; a reply that doesn't fit, sent through the real prompt and parser, becomes the 502
  `Gemini didn't answer (OutputParserException).`; the page is served at `/` and `/index.html` with no key in it,
  and checks `res.ok` when it opens and on each submit.
- **Live (2 tests)**: a Spanish greeting comes back as a `Greeting`, and the sample message is sorted as `billing`.

That's 23 plain tests and 2 live ones.

```bash
python -m pytest                     # all 25; with no key: 23 passed, 2 skipped
python -m pytest -m "not live"       # only the 23 plain ones: no call, no cost
python -m pytest -m live             # only the 2 live ones: two real calls to Gemini
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No key: no `.env` and no `GOOGLE_API_KEY` | `python hello.py` and `uvicorn main:app` stop at once: `Can't build the chain: GOOGLE_API_KEY is not set. ...` | Copy the key as in [Before you start](#before-you-start) |
| A bad input: an empty name, a language that isn't in the list, a message over 1,000 characters | A 422, and Gemini is never called. The page shows the field and the problem, e.g. `name: String should have at least 1 character` | Fix the input |
| Gemini doesn't answer: a wrong key, the free tier's per-minute limit, no network | A 502. The page shows `Gemini didn't answer (...)` with the error's type, e.g. `GoogleInvalidRequestError` for a wrong key, and the server's terminal shows the full reason, e.g. `API key not valid` | Check the key in `.env` ([project 9](../09-gemini-key/README.md)), or wait a minute and try again |
| Gemini answers, but its JSON doesn't fit the schema, or was cut off at `MAX_OUTPUT_TOKENS` | A 502 too: `Gemini didn't answer (OutputParserException).` Here "didn't answer" means no usable answer: the parser refused it, so bad data never reaches the page. The terminal shows `Gemini call failed: Failed to parse Greeting from completion {...}. Got: 1 validation error for Greeting ...` | Try again. If the terminal says the last fields are `Field required`, often after a value that stops mid-sentence, the answer was most likely cut off at the cap: raise `MAX_OUTPUT_TOKENS` in `hello.py`. (The parser closes cut-off JSON before it checks it, so the JSON shown doesn't stop half-way.) |
| A wrong key with `python hello.py` | A long traceback that ends in `GoogleInvalidRequestError` and `API key not valid`: only a missing key gets the short message | Check the key in `.env` |
| `python hello.py` in Git Bash on Windows stops after its first line | A traceback that ends in `UnicodeEncodeError: 'charmap' codec can't encode characters ...` | The greeting is in Hindi and has an emoji. Git Bash hands Python a pipe, so Python writes in Windows' older code page (often cp1252), which has neither. Run `PYTHONUTF8=1 python hello.py`, or `export PYTHONUTF8=1` once per terminal |

With native structured output, the fourth row should be rare: Gemini is made to write JSON of the right shape. One
way it can still happen: an answer cut off at `MAX_OUTPUT_TOKENS` is missing its last fields. The check is there
anyway, and it's free.

You may also see `Direct use of automatic function calling (AFC) ... is not recommended` in the terminal. That's the
`google-genai` library talking to itself, and it does no harm.

## Things to try

1. **See exactly what Gemini is told, with no call.** Print the schema that goes with every ticket request as
   `response_json_schema`:

   ```bash
   python -c "import json, hello; print(json.dumps(hello.Ticket.model_json_schema(), indent=2))"
   ```

   You see the class docstring as the top `description`, the four properties (three of them with an `enum` list of
   choices), the urgency rule, and the `required` list. Importing `hello` needs the key, but nothing is sent.
2. **See the raw reply next to the object.** Add these lines at the end of `hello.py`'s main block, then run
   `python hello.py` (one more call):

   ```python
       raw_chain = greet_prompt | model.with_structured_output(Greeting, include_raw=True)
       result = raw_chain.invoke({"name": "Asha", "language": "Hindi"})
       print(result["raw"].text)          # the JSON text Gemini wrote
       print(result["parsed"])            # the Greeting made from it, or None if it didn't fit
       print(result["parsing_error"])     # None, or the OutputParserException
   ```

   You see the JSON string, the `Greeting` made from it, and `None`. With `include_raw=True`, a reply that doesn't
   fit doesn't raise: `parsed` is `None`, and `parsing_error` holds the error.
3. **Try the other method.** In `hello.py`, change the greeting chain to
   `model.with_structured_output(Greeting, method="function_calling")` and run `python -m pytest -m "not live"`:
   5 tests fail and 18 pass. The model step now carries `tools` and `tool_choice` instead of `response_mime_type`,
   and the last step is a `PydanticToolsParser`: Gemini is asked to call a "tool" whose arguments are the fields.
   The library's own docs call this way less reliable than the default. Change it back.
4. **Add a field.** Add `farewell: str = Field(description="A short goodbye, in the same language")` to `Greeting`.
   `/docs` now shows five fields, and with your key the page shows five boxes, with no change to `index.html`.
   `python -m pytest -m "not live"` now fails 4 tests: the test data and the `required` list still have four
   fields, so the tests notice when the shape changes. Take it out again.

## Next

**[Project 16 · Reasoning: chain-of-thought and thinking](../16-gemini-reasoning/README.md)**: ask the same
multi-step questions three ways (directly, step by step, and with Gemini's thinking turned up), and measure how many
each gets right and what it costs in tokens and time.
