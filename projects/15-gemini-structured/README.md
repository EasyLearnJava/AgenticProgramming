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

## What you learn

- **`model.with_structured_output(Greeting)`**: ask for an object of a Pydantic class, and get one back
- **A Pydantic class as a schema for the model**: field types, `Literal` choices, and descriptions Gemini reads
- **JSON mode**: Gemini is told to answer in JSON of exactly that shape
- **Messy text → clean data** that code can act on: `if ticket.urgency == "high": ...`

## Before you start: the key

As in project 10, copy your `.env` across (or use a Codespaces secret):

```bash
cd projects/15-gemini-structured
cp ../10-gemini-llm/.env .env
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `hello.py` | The two classes, `Greeting` and `Ticket`; the two prompts; and the two chains, `greet_chain` and `triage_chain`. `python hello.py` prints one of each, field by field |
| `config.py` | Loads and checks the key: the same file as projects 9 to 14 |
| `main.py` | FastAPI: `POST /api/greet` and `POST /api/triage` return the objects as JSON (`response_model`), and `GET /api/setup` gives the page its dropdown and sample message |
| `index.html` | The page: each field of the answer in its own box |
| `tests/conftest.py` | Skips the live tests when there is no key |
| `tests/test_hello.py` | 21 plain tests (no call) and 2 live tests (two real calls) |
| `requirements.txt` | The same as project 10 |

## The shape you want back

```python
class Greeting(BaseModel):
    """A short welcome for someone starting to learn LangChain."""
    message: str = Field(description="The welcome itself, one or two sentences, written in the requested language")
    language: Literal["English", "Hindi", "Telugu", "Tamil", "Spanish", "French"]
    emoji: str = Field(description="One emoji that fits the message")
    tone: Literal["warm", "playful", "formal"] = Field(description="How the message sounds")
```

Each part tells Gemini something:

| Part | Tells Gemini |
|---|---|
| The field names and types | Which keys to fill in, and what kind of value goes in each |
| `Literal["warm", "playful", "formal"]` | One of these, and nothing else |
| `Field(description=...)` | What the field is for: it reads like an instruction |
| The class docstring | What the whole object is |

Pydantic does the same job here as for FastAPI's request bodies since project 4, but the other way round: there it
checked what **the page** sent, and here it checks what **Gemini** sends back.

## What `with_structured_output` does

```python
greet_chain = greet_prompt | model.with_structured_output(Greeting)

greeting = greet_chain.invoke({"name": "Asha", "language": "Hindi"})
type(greeting)        # <class 'hello.Greeting'>, not a str
greeting.tone         # "warm"
```

It adds two things to the chain, and a test checks both:

1. **The model, told to answer in JSON.** The request to Gemini gets `response_mime_type: application/json` and a
   JSON schema made from the class (`Greeting.model_json_schema()`): the fields, their types, their choices, their
   descriptions, and which ones are required. Gemini writes its answer to fit that schema.
2. **A parser**, `PydanticOutputParser`, which reads the JSON and builds a `Greeting` from it. If anything doesn't
   fit, like a missing field or `"tone": "angry"`, it raises an error instead of handing you bad data.

So there's no `StrOutputParser` and no text to search through: the chain gives you the object.

## The prompts don't describe the format

```python
greet_prompt = ChatPromptTemplate.from_messages([
    ("system", "You write short, friendly welcomes for people who are starting to learn LangChain."),
    ("human", "Write a welcome for {name}, in {language}."),
])
```

No "answer in JSON with these keys": the schema already says that, exactly. The prompt only says what to write.
Compare it with project 14, where the format had to be shown with examples and checked with `follows_format()`.

## Messy text into a ticket

```python
class Ticket(BaseModel):
    intent: str = Field(description="What the customer wants, in at most ten words")
    category: Literal["billing", "technical", "account", "shipping", "other"]
    urgency: Literal["low", "medium", "high"] = Field(description="high: money lost, or the customer can't use ...")
    route_to_team: Literal["billing_team", "support_engineers", "account_team", "logistics", "general_support"]
```

The sample message is in lower case, with typos, shouting, and two problems at once (a double charge and a late
jacket). The ticket that comes back has only fixed choices, so code can act on it without reading the text:

```python
if ticket.urgency == "high":
    notify(ticket.route_to_team, ticket.intent)
```

The `urgency` description gives the rule for each level. Without it, "high" would be Gemini's guess.

## When things go wrong

| What happens | What you see |
|---|---|
| A bad name, an unknown language, a message over 1,000 characters | A 422, and Gemini is never called |
| Gemini doesn't answer (bad key, quota) | A 502: `Gemini didn't answer (...)` |
| Gemini answers with data that doesn't fit the schema | A 502 too: the parser refuses it, so bad data never reaches the page |

With JSON mode, the third case should be rare: Gemini is made to write JSON of the right shape. The check is there
anyway, and it's free.

## Run it

```bash
cd projects/15-gemini-structured
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../10-gemini-llm/.env .env      # the key, once (see above)

python hello.py                    # one greeting and one ticket, field by field
python -m pytest                   # 23 tests: 21 plain, 2 live
python -m pytest -m "not live"     # only the plain ones: no call, no cost

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

`/docs` shows the exact shape of each answer, taken from the same `Greeting` and `Ticket` classes.

```bash
curl -X POST http://127.0.0.1:8000/api/greet -H "Content-Type: application/json" \
     -d '{"name": "Asha", "language": "Hindi"}'
curl -X POST http://127.0.0.1:8000/api/triage -H "Content-Type: application/json" \
     -d '{"message": "my app keeps crashing when i log in, i cant use it at all"}'
```

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Part B's next module is about reasoning: letting the model think step by step, and keeping track of prompt
versions.
