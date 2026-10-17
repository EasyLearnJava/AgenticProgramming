# 14 · Show, don't tell: few-shot examples

Instead of describing the format you want, show it: put two or three example answers in the prompt, and Gemini
copies them. The page asks 10 questions twice, without and with the examples, and checks each answer's format in
code, so you can count the difference.

```text
"What is a list?"
  without examples:  **Lists in Python**                         with examples:  In one line: A list holds items in order.
                     A list is a collection that ...                             Example: names = ["Asha", "Ravi"]
                     ### Key features                                            Watch out: The first item is at index 0, not 1.
                     - ordered  - changeable ...                ✘ format         ✔ format
                     (made-up examples: Gemini's words change every time)
```

## What you learn

- **Few-shot prompting**: example question → answer pairs in the prompt, so the model copies their format and tone
- **`FewShotChatMessagePromptTemplate`**: turns a list of examples into messages
- **Examples vs instructions**: the system prompt here never mentions the format; only the examples show it
- **Checking the format in code**: `follows_format()` turns "does it look right?" into a number you can compare

## Before you start: the key

As in project 10, copy your `.env` across (or use a Codespaces secret):

```bash
cd projects/14-gemini-few-shot
cp ../10-gemini-llm/.env .env
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `hello.py` | The system prompt, the three `EXAMPLES`, the 10 `QUESTIONS`, `follows_format()`, the two prompts, and the chain that runs both. `python hello.py` runs all 10 and prints the score |
| `config.py` | Loads and checks the key: the same file as projects 9 to 13 |
| `main.py` | FastAPI: `GET /api/setup` gives the page the prompt, examples and questions; `POST /api/compare` asks 1 to 10 questions both ways and checks each answer |
| `index.html` | The page: the examples, a box of questions, and a table with ✔ or ✘ for each answer, plus the score |
| `tests/conftest.py` | Skips the live test when there is no key |
| `tests/test_hello.py` | 23 plain tests (no call) and 1 live test (two real calls) |
| `requirements.txt` | The same as project 10 |

## The examples

```python
EXAMPLES = [
    {"question": "What is a variable?",
     "answer": "In one line: A variable is a name that holds a value, so you can use it later.\n"
               "Example: age = 30 stores 30 under the name age.\n"
               "Watch out: In Python, = stores a value and == compares two values."},
    {"question": "What is a loop?", "answer": "In one line: ...\nExample: ...\nWatch out: ..."},
    {"question": "What is a function?", "answer": "In one line: ...\nExample: ...\nWatch out: ..."},
]

example_prompt = ChatPromptTemplate.from_messages([("human", "{question}"), ("ai", "{answer}")])
few_shot = FewShotChatMessagePromptTemplate(examples=EXAMPLES, example_prompt=example_prompt)

with_examples = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), few_shot, ("human", "{question}")])
without_examples = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{question}")])
```

`example_prompt` says how one example becomes messages: its question as a human message, and its answer as an AI
message. So Gemini sees a short conversation in which it has already answered three questions in that format:

```text
system:  You answer programming questions for beginners.
human:   What is a variable?
ai:      In one line: ... / Example: ... / Watch out: ...      ┐
human:   What is a loop?                                        │  the three examples
ai:      In one line: ... / Example: ... / Watch out: ...       │
human:   What is a function?                                    │
ai:      In one line: ... / Example: ... / Watch out: ...      ┘
human:   What is a list?                                          the real question
```

The model continues the pattern. The real question is the last human message, so its answer comes next.

## Good examples agree with each other

The three examples share everything you want copied: the same three labels, in the same order, one line each,
about the same length, and plain text with no bold or lists. If one example used bullet points and another used
labels, Gemini would get a blurred picture and mix the two. A test checks that every example follows the format
it's teaching.

The 10 test questions are all different from the examples, so the model has to apply the format rather than repeat
an answer.

## Checking the format in code

```python
LABELS = ("In one line:", "Example:", "Watch out:")

def follows_format(answer: str) -> bool:
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    return len(lines) == 3 and all(line.startswith(label) for line, label in zip(lines, LABELS))
```

Exactly three non-blank lines, starting with the three labels, in order. It's strict on purpose: `**In one line:**`
in bold doesn't count, because the examples aren't bold. Code that reads these answers later would need the exact
labels too.

## Examples or instructions?

You could also write the format into the system prompt: "Answer in three lines: In one line…, Example…, Watch
out…". Both work, and they work best together. Examples are better at the details that are hard to describe: the
length of a line, the tone, how small an example should be. Instructions are better at rules: "never include code
longer than one line". This project leaves the format out of the system prompt on purpose, so the difference you
see comes only from the examples.

## The free tier and 20 calls

Comparing 10 questions makes 20 calls. The server runs at most 2 questions at a time (`max_concurrency=2`), so at
most 4 calls at once. On the free tier, Gemini limits how many requests you can make per minute. If you go over,
those questions show `Gemini didn't answer (...)` in their row while the others still come back. Wait a minute,
or compare fewer questions.

## Run it

```bash
cd projects/14-gemini-few-shot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../10-gemini-llm/.env .env      # the key, once (see above)

python hello.py                    # all 10 questions both ways, then: without examples N of 10, with examples N of 10
python -m pytest                   # 24 tests: 23 plain, 1 live
python -m pytest -m "not live"     # only the plain ones: no call, no cost

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

```bash
curl -X POST http://127.0.0.1:8000/api/compare -H "Content-Type: application/json" \
     -d '{"questions": ["What is a list?", "What is a string?"]}'
```

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Structured output: instead of text in a format, Gemini returns typed data, with every field checked by Pydantic.
