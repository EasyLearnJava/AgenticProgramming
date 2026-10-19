# 14 · Show, don't tell: few-shot examples

Instead of describing the format you want, show it: put three example answers in the prompt, and Gemini tends to
copy them. The script and the page ask 10 questions twice, without and with the examples, and check each answer's
format in code, so you can count the difference.

```text
"What is a list?"
  without examples:  **Lists in Python**
                     A list is a collection that ... ### Key features ...    ✘ not the format
  with examples:     In one line: A list holds items in order.
                     Example: names = ["Asha", "Ravi"]
                     Watch out: The first item is at index 0, not 1.         ✔ the format
                     (made-up answers: Gemini's words change every time)
```

## What you'll build

- `python hello.py`: asks Gemini the 10 questions twice, first with only a plain system prompt, then with three
  example answers in front of each question. It prints every answer marked "follows the format" or "does NOT follow
  the format", then how many questions Gemini answered and the two scores.
- A FastAPI server: `GET /api/setup` gives the system prompt, the examples and the 10 default questions, and
  `POST /api/compare` asks 1 to 10 questions both ways. It sends back one row per question: both answers, each with
  a true/false flag for the format, or an error row.
- A page with the system prompt, the examples, a box of questions, and a table with ✔ or ✘ for every answer, plus
  the score.

## What you'll learn

- **Few-shot prompting**: example question → answer pairs in the prompt, so the model tends to copy their format
  and tone
- **`FewShotChatMessagePromptTemplate`**: turns a list of example dicts into human/AI message pairs, which Gemini
  receives as earlier turns of the conversation
- **Examples vs instructions**: the system prompt here never mentions the format, so the difference comes from the
  examples alone
- **Checking model output in code**: `follows_format()` turns "does it look right?" into ✔ or ✘, and a score
- **`batch()` with `return_exceptions=True`**: 10 questions are 20 calls, at most 4 at once, and a question Gemini
  didn't answer becomes one error row instead of stopping everything

## What's new since project 13

- [Project 13 · Give the model a role: the system prompt](../13-gemini-system-prompt/README.md) changed the answers
  with two system prompts. Here there is one plain system prompt, and three example answers, placed between it and
  the question, change them.
- The `ai` role, which project 13 only described, is now written by you: each example answer is an AI message, as
  if Gemini had already answered that way.
- The answers are checked in code, with `follows_format()`, instead of by eye.
- From one question to ten: `batch()` and `abatch()` from project 7, with the new `return_exceptions=True`. A
  question Gemini didn't answer is an error row in a 200, where project 13 answered 502. The body is a list of
  questions, and `Annotated[str, StringConstraints(...)]` puts the rules on each one.

## Before you start

- Python 3.11 or newer.
- The Gemini key from [project 9](../09-gemini-key/README.md). Each project folder has its own `.env`, so copy it
  across once (or use a Codespaces secret named `GOOGLE_API_KEY`, which every project sees):

```bash
cd projects/14-gemini-few-shot
cp ../09-gemini-key/.env .env
```

## Files

| File | What it is |
|---|---|
| `hello.py` | The system prompt, the three `EXAMPLES`, the 10 `QUESTIONS`, `follows_format()`, the two prompts, and the chain that runs both. `python hello.py` asks all 10 and prints the scores |
| `main.py` | FastAPI: `GET /` and `/index.html` serve the page, `GET /api/setup` gives it the prompt, examples and questions, and `POST /api/compare` asks 1 to 10 questions both ways and checks each answer. A bad list gets a 422 before any call; a question Gemini didn't answer becomes an error row |
| `index.html` | The page: the system prompt, the examples, a box of questions, and a table with ✔ or ✘ for each answer, plus the score |
| `config.py` | Loads and checks the key: the same file in every project from 9 on |
| `.env.example` | The template for `.env`, if you write the key file by hand (`.env` itself is in `.gitignore`) |
| `tests/test_hello.py` | The tests: plain ones that make no call, and the live test (two real calls) |
| `tests/conftest.py` | Checks once for a real key: with none, it gives `hello.py` a fake one and skips the live test |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, looks only in `tests/`, and defines the `live` marker |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core`, `langchain-google-genai`, `google-genai`, `python-dotenv`: the same as project 10 |
| `requirements-dev.txt` | `requirements.txt` plus `pytest` and `httpx`, for the tests |
| `README.md` | This file |

## How it works

### One plain system prompt, and a cap

```python
MODEL = "gemini-3.5-flash-lite"
# The cap on each answer (project 11). The three-line format needs far less; a longer answer is cut off at the cap.
MAX_OUTPUT_TOKENS = 200

# The same short system prompt for both. It says what to do, but nothing about the format: only the examples show it.
SYSTEM_PROMPT = "You answer programming questions for beginners."
```

Both prompts use this one system prompt. It never mentions the format (a test checks that none of the labels appear
in it), so the difference between the two columns comes from the examples.

### ① The examples

```python
EXAMPLES = [
    {
        "question": "What is a variable?",
        "answer": "In one line: A variable is a name that holds a value, so you can use it later.\n"
                  "Example: age = 30 stores 30 under the name age.\n"
                  "Watch out: In Python, = stores a value and == compares two values.",
    },
    ...
]
```

The other two, "What is a loop?" and "What is a function?", have the same shape. Good examples agree with each
other: they share everything you want copied. Here that's the same three labels, in the same order, one line each,
about the same length, and plain text with no bold or lists. If one example used bullet points and another used
labels, the model could mix the two. A test checks that every example follows the format it teaches.

The 10 `QUESTIONS` are all different from the examples, so the model has to apply the format rather than repeat an
answer.

### ② Checking the format in code

```python
LABELS = ("In one line:", "Example:", "Watch out:")


# ② The check: exactly three lines, starting with the three labels in order. Plain code, no model.
def follows_format(answer: str) -> bool:
    lines = [line.strip() for line in answer.splitlines() if line.strip()]      # the non-blank lines, trimmed
    # zip() pairs line 1 with label 1, line 2 with label 2, ... and stops at the shorter of the two. So the count is
    # checked first: otherwise an answer with only the first two lines, or with an extra fourth line, would pass.
    return len(lines) == len(LABELS) and all(line.startswith(label) for line, label in zip(lines, LABELS))
```

Exactly three non-blank lines, starting with the three labels, in order; blank lines and spaces around them don't
matter. It's strict on purpose: `**In one line:**` in bold doesn't count, because the examples aren't bold, and code
that reads these answers later would need the exact labels too. This turns "does it look right?" into ✔ or ✘, and
a score you can compare.

### ③ From examples to messages

```python
example_prompt = ChatPromptTemplate.from_messages([("human", "{question}"), ("ai", "{answer}")])
few_shot = FewShotChatMessagePromptTemplate(examples=EXAMPLES, example_prompt=example_prompt)
```

`example_prompt` says how one example becomes messages: its question as a human message, and its answer as an AI
message. `few_shot` does that for each dict in `EXAMPLES`. Its `{question}` and `{answer}` are filled from those
dicts (so the keys must match), never from the user's input: `few_shot` needs no input at all.

So the "with examples" prompt is a short conversation in which Gemini seems to have answered three questions in
that format already (`/` marks a line break):

```text
system:  You answer programming questions for beginners.
human:   What is a variable?                                   ┐
ai:      In one line: ... / Example: ... / Watch out: ...      │
human:   What is a loop?                                       │  the three examples
ai:      In one line: ... / Example: ... / Watch out: ...      │
human:   What is a function?                                   │
ai:      In one line: ... / Example: ... / Watch out: ...      ┘
human:   What is a list?                                          the real question
```

`langchain-google-genai` sends the system message as Gemini's `system_instruction`, each human message as a `user`
turn and each AI message as a `model` turn. So to Gemini, the examples look like answers it gave earlier in this
conversation. The real question is the last message, so its answer comes next, and models tend to continue the
pattern: the score shows how often Gemini does.

### ④ Two prompts, one difference

```python
without_examples = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{question}")])
with_examples = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), few_shot, ("human", "{question}")])
```

The only difference is `few_shot`, between the system message and the real question. It sits in the list like one
more message; when the prompt is filled in, it becomes the six example messages (three human, three AI). Both
prompts still need only the user's `{question}`. The tests check the order of both: system, then human for one;
system, then human and AI three times, then human for the other.

### ⑤ Both prompts for each question, side by side

```python
chain = RunnableParallel({
    "without": without_examples | model | StrOutputParser(),
    "with": with_examples | model | StrOutputParser(),
})
```

`RunnableParallel` (project 6) runs both for one question: two calls at the same time, and one result,
`{"without": "...", "with": "..."}`.

### Ten questions at once, and the ones Gemini doesn't answer

`python hello.py` runs the chain for all ten questions with `batch()` from project 7:

```python
    results = chain.batch([{"question": q} for q in QUESTIONS], config={"max_concurrency": 2}, return_exceptions=True)
```

and `main.py` does the same with `abatch()`, `batch()`'s async twin:

```python
    results = await chain.abatch(
        [{"question": q} for q in body.questions],
        config={"max_concurrency": 2},
        return_exceptions=True,          # one failed question becomes an error in its row, not a failed page
    )
```

A list in, a list out, in the same order. `max_concurrency=2` lets 2 questions run at once, and each question is 2
calls, so at most 4 calls run at the same time.

`return_exceptions=True` is new. Without it, one refused call raises out of `batch()` and every other answer is
lost, even though many of the calls may already have been made, using your quota. With it, a question Gemini didn't
answer comes back as its error, in its place in the list. It's per question, not per call: if either of a
question's two calls fails, the whole question comes back as that error, even when the other call worked (both
answers or neither, as in project 13). `python hello.py` prints the error under that question and goes on.
`compare()` turns it into an error row:

```python
        if isinstance(result, Exception):
            # The full reason goes to the server's terminal; the page only learns the error's type.
            logger.warning("Gemini call failed for %r: %s", question, result)
            rows.append({"question": question, "error": f"Gemini didn't answer ({type(result).__name__})."})
            continue
```

That's why this server answers 200 with an error row where project 13 answered 502: one refused call shouldn't throw
away the other questions' answers. As in project 13, the full reason goes to the server's terminal, and the page
only learns the error's type.

### The request and the page

```python
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CompareIn(BaseModel):
    """1 to 10 questions. Each one is two Gemini calls, so 10 questions are 20 calls."""
    questions: list[Question] = Field(min_length=1, max_length=10)
```

`Question` holds the rules for one question. `Annotated[str, ...]` is still a `str`, with rules attached: spaces
trimmed first, then 1 to 200 characters. `list[Question]` puts those rules on every item, and
`Field(min_length=1, max_length=10)` puts its own on the list. A bad list gets a 422, and Gemini is never called.

The page sends the box's non-blank lines. For each row that comes back, it shows both answers with ✔ or ✘ (from
`without_ok` and `with_ok`), or the error across the row. Then it counts the ✔ and shows
`Followed the format: without examples N of M, with examples N of M.`, plus how many questions got no answer. If
no question got an answer, it says `Gemini didn't answer any question. The server's terminal says why.`

### Examples or instructions?

You could also write the format into the system prompt: "Answer in three lines: In one line…, Example…, Watch
out…" ([Things to try](#things-to-try) does that). The two are often used together. Examples are better at the
details that are hard to describe: the length of a line, the tone, how small an example should be. Instructions are
better at rules: "never include code longer than one line". This project leaves the format out of the system prompt
on purpose, so the difference you see comes only from the examples.

## Run it

```bash
cd projects/14-gemini-few-shot
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the `.env` copied (see [Before you start](#before-you-start)):

```bash
python config.py                     # GOOGLE_API_KEY is set.
python hello.py                      # all 10 questions both ways: 20 calls
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

`python hello.py` prints each question's two answers, then the score:

```text
=== What is a list?
--- without examples: does NOT follow the format
**Lists in Python**
...
--- with examples: follows the format
In one line: A list holds items in order.
Example: names = ["Asha", "Ravi"]
Watch out: The first item is at index 0, not 1.
...
Gemini answered 10 of 10 questions.
without examples: 0 of 10 answers follow the format
with examples: 10 of 10 answers follow the format
(made-up answers and numbers: yours will differ)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

The curl examples are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl http://127.0.0.1:8000/api/setup
curl -X POST http://127.0.0.1:8000/api/compare -H "Content-Type: application/json" \
     -d '{"questions": ["What is a list?", "What is a string?"]}'
```

Each question is two real calls to Gemini, so the page's ten default questions are 20.

## Test it

The plain tests make no call to Gemini, so they need no key and cost nothing. They check:

- `follows_format()`: three shapes pass (the format, with blank lines around it, with blank lines between) and five
  fail (free text, the wrong order, a missing label, an extra line, bold labels)
- the setup: every example follows the format it teaches, the system prompt names none of the labels, and there are
  10 questions, none of them an example
- the two prompts' message order, the chain's two branches, and the model settings (`gemini-3.5-flash-lite`, at
  most 200 tokens per answer)
- with no key, `python hello.py` stops with the message, not a traceback
- the script, with a stand-in for Gemini that refuses one question: it prints that question's error, goes on, and
  ends with `Gemini answered 9 of 10 questions.` and the two scores
- the endpoints, with a stand-in chain: `GET /api/setup`; `POST /api/compare` trims each question and flags each
  answer; a failed question becomes an error row; an empty list, 11 questions, a blank question and a 201-character
  question each get a 422 and no call
- the page is served at `/` and `/index.html`, and holds no key

The live test asks two questions with examples (two real calls) and checks that both answers follow the format. It
is skipped when there's no key.

That's 27 tests: 26 plain and 1 live. Without a key, `python -m pytest` shows `26 passed, 1 skipped`.

```bash
python -m pytest                     # every test; the live one runs only when a key is found
python -m pytest -m "not live"       # only the plain ones: no call, no cost
python -m pytest -m live             # only the live one: two real calls
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No key | `python hello.py` stops with `Can't build the chain: GOOGLE_API_KEY is not set. ...`; `uvicorn main:app --reload` prints the same message but keeps waiting, and the page doesn't load | Copy the `.env` across (see [Before you start](#before-you-start)), then stop the server (Ctrl+C) and start it again |
| A wrong key | Every row says `Gemini didn't answer (GoogleInvalidRequestError).`, and the page says `Gemini didn't answer any question. The server's terminal says why.` The terminal says `API key not valid`, and so does `python hello.py` | Fix the key in `.env`, then stop the server (Ctrl+C) and start it again: `--reload` only watches `.py` files |
| The free tier's per-minute limit | The page or the script waits about half a minute while the Google SDK quietly tries a refused call again (up to 6 tries in all). If it's still refused, that question says `Gemini didn't answer (GoogleRateLimitError).`, and the others still come back | Wait a minute, or compare fewer questions |
| An empty box, 11 questions, or a question over 200 characters | A 422, and Gemini is never called. The page shows FastAPI's message, like `questions: List should have at most 10 items after validation, not 11`. For a question that's too long, the message starts with its place in the list, counting from 0: `3: String should have at most 200 characters` means the 4th question (the page skips blank lines) | Fix the list |
| A "with examples" answer gets ✘ | The cell shows bold labels, a heading or a fourth line | Nothing to fix: `follows_format()` is strict on purpose. Count the ✔ to compare the two columns |
| `python hello.py` in Git Bash on Windows stops with a traceback | `UnicodeEncodeError: 'charmap' codec can't encode character ...` | An answer has a character such as → or an emoji, and Python writes to Git Bash in Windows' older code page (often cp1252), which has neither. Run `PYTHONUTF8=1 python hello.py`, or `export PYTHONUTF8=1` once per terminal |

## Things to try

1. **Put the format in the instructions too.** In `hello.py`, change the system prompt to:

   ```python
   SYSTEM_PROMPT = ("You answer programming questions for beginners. Answer in exactly three lines that start with "
                    '"In one line:", "Example:" and "Watch out:".')
   ```

   `python -m pytest -m "not live"` now fails one test, `test_the_system_prompt_does_not_describe_the_format`,
   because the instructions now teach the format too. Run `python hello.py` and compare the "without examples"
   score with the one you got before.
2. **Break one example.** In the "What is a loop?" example, change `"Example: for name in` to
   `"**Example:** for name in`. `python -m pytest -m "not live"` fails one test,
   `test_every_example_follows_the_format_it_teaches`, with `AssertionError: What is a loop?`: that example would
   now teach bold labels, which `follows_format()` refuses.
3. **One example instead of three.** Delete the "What is a loop?" and "What is a function?" dicts from `EXAMPLES`.
   All the plain tests still pass, and the page shows one example. Run `python hello.py` and compare the "with
   examples" score.
4. **Send a bad list.** Add an 11th question to the page's box and click **Compare**. The page shows
   `questions: List should have at most 10 items after validation, not 11`, and the server's terminal shows only a
   `"POST /api/compare HTTP/1.1" 422` line (`Unprocessable Content`, or `Unprocessable Entity` before Python 3.13),
   with no warning: Gemini was never called.

## Next

**[Project 15 · Structured output](../15-gemini-structured/README.md)**: instead of text in a format that
`follows_format()` has to check, Gemini returns a Pydantic object with every field typed and checked.
