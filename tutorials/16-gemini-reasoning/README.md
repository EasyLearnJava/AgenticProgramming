# 16 · Reasoning: chain-of-thought and thinking

Some questions need a few steps, and a model that answers straight away can get them wrong, just as a person can.
This project asks six multi-step word problems three ways, checks every answer in code, and measures what reasoning
first buys you and what it costs; a second part takes one badly written prompt and fixes it.

```text
6 questions × 3 ways = 18 calls to Gemini  ->

                 right    avg output tokens    avg thinking tokens    avg time
direct           4 of 6          5                    0                 500 ms
step_by_step     6 of 6        150                    0                1800 ms
thinking         6 of 6        420                  410                2600 ms
(made-up numbers: Gemini's answers, tokens and times change every run)
```

## What you'll build

- `hello.py`, a script that makes 20 calls: each of the six questions three ways (right or WRONG, output tokens,
  thinking tokens, time), a summary line per way, then a messy prompt and its fixed version on the same customer
  message.
- A FastAPI server: `GET /api/setup` gives the page what to show, `POST /api/compare` runs the 18 calls, at most 4 at
  a time, and `POST /api/fix` tries both prompts at once.
- A plain page: the three ways' prompts, a **Run all** button that fills a summary table and a row per question (open
  "the answer" to read what Gemini wrote), and the two prompts with their answers side by side.

## What you'll learn

- **Chain-of-thought**: asking the model, in the prompt, to work through the steps before it answers
- **Thinking**: a setting that makes the model reason privately before it writes its answer (`thinking_level`)
- **What reasoning costs**: more output tokens and more time, which a table makes visible
- **Checking answers in code**: every answer ends with `Answer: <number>`, and `read_answer()` reads it
- **`asyncio.gather` and `asyncio.Semaphore`**: start 18 calls at once, but let only 4 run at the same time
- **Four prompt anti-patterns**, and how to fix them

## What's new since project 15

- [Project 15 · Structured output](../15-gemini-structured/README.md) got typed objects back. This one goes back to
  plain text, because the steps should come first, as ordinary writing; code then reads only the last line,
  `Answer: <number>`, with `read_answer()`.
- A new model setting, `thinking_level`, set for one chain with `model.bind()`, as `max_output_tokens` was in
  project 11. The thinking tokens that project 11 showed as a column are now what's being measured.
- The first async functions in `hello.py`: `ask()` and `compare()` run the 18 calls with `asyncio.gather` and an
  `asyncio.Semaphore`, instead of `batch(config={"max_concurrency": ...})` as in projects 7 and 14.
- `main.py` writes `import hello` and uses `hello.<name>`, instead of importing names from it, and the tests swap
  `hello.chains`, `hello.before_chain` and `hello.after_chain` for stand-ins. The sample customer message is the one
  from project 15.

## Before you start

- Python 3.11 or newer.
- Your Gemini key from [project 9](../09-gemini-key/README.md), copied into this folder once:

  ```bash
  cd tutorials/16-gemini-reasoning
  cp ../09-gemini-key/.env .env
  ```

  In GitHub Codespaces, a Codespaces secret named `GOOGLE_API_KEY` does the same job, with no file.

## Files

| File | What it is |
|---|---|
| `hello.py` | The six `QUESTIONS`, the three `WAYS` and their chains, `read_answer()`, `ask()` and `compare()` (at most `AT_ONCE` calls at a time), `summary()`; then the prompt before and after. `python hello.py` runs it all |
| `main.py` | FastAPI: `GET /api/setup` gives the page what to show, `POST /api/compare` runs the 18 calls, `POST /api/fix` tries both prompts |
| `index.html` | The page: the three ways, a summary table, a row per question (open "the answer" to read it), and the before/after |
| `config.py` | Loads and checks the key: the same file in every project from 9 on |
| `.env.example` | The template for `.env`: `GOOGLE_API_KEY=your-key-here`. Your real `.env` is in `.gitignore`, so it never goes into git |
| `tests/test_hello.py` | The tests: plain ones that make no call, and live ones that call Gemini |
| `tests/conftest.py` | Skips the live tests when there is no key |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, looks only in `tests/`, and defines the `live` marker |
| `requirements.txt` | The packages the project needs: the same as project 10 |
| `requirements-dev.txt` | `requirements.txt` plus pytest and httpx, for the tests |
| `README.md` | This file |

## How it works

### ① Six questions, each with one right number

```python
# ① Questions with one right number each. Several are classic traps: the quick answer that comes to mind is wrong.
QUESTIONS = [
    {"question": "A bat and a ball cost 110 rupees in total. The bat costs 100 rupees more than the ball. "
                 "How many rupees does the ball cost?", "answer": 5},
    ...
]
```

Six word problems. Several are well-known traps, where the first answer that comes to mind is wrong:

| Question (short) | The quick answer | The right answer |
|---|---|---|
| A bat and a ball cost 110; the bat costs 100 more. The ball? | 10 | **5** (ball 5 + bat 105 = 110) |
| 3 boxes of 12 apples, give away a third, buy 7 | | **31** |
| 5 machines make 5 widgets in 5 minutes; 100 machines, 100 widgets? | 100 | **5** |
| Lily pads double daily and cover the lake on day 48; half? | 24 | **47** |
| 800, cut by 25%, then up by 10% | 680 | **660** |
| 15 pages Monday, 5 more each day; total by Friday? | | **125** |

### ② Three ways: a prompt or a setting

```python
ANSWER_LINE = 'End with one line in the form "Answer: <number>", with only the number on it.'

# ② The three ways. Only the system prompt and the thinking level change; the question is the same.
WAYS = {
    "direct": {
        "system": f"You solve maths word problems. Reply with only the answer. {ANSWER_LINE}",
        "thinking_level": None,                      # the model's default: "minimal" for this model
    },
    "step_by_step": {
        "system": f"You solve maths word problems. Work through the problem step by step, "
                  f"writing each step on its own line, then check your result. {ANSWER_LINE}",
        "thinking_level": None,
    },
    "thinking": {
        "system": f"You solve maths word problems. Reply with only the answer. {ANSWER_LINE}",
        "thinking_level": "high",                    # the model reasons privately before it writes the answer
    },
}
```

| Way | What changes | Where the reasoning goes |
|---|---|---|
| `direct` | nothing: answer at once | nowhere, or almost: `minimal` thinking is small or 0 |
| `step_by_step` | the **prompt** asks for steps | into the answer you can read, as visible text |
| `thinking` | the **setting** `thinking_level="high"`; the prompt is the same as `direct` | into hidden thinking tokens you don't see, but do pay for |

`direct` and `thinking` have exactly the same prompt, so any difference between them comes from the setting.

**Chain-of-thought: reasoning in the prompt.** A model writes one token after another, and each token can only
build on what's already written. Asking for steps first gives it room: the working-out is written before the
answer, so the answer can build on it. Those steps are ordinary output: you can read them, and they cost output
tokens.

**Thinking: reasoning as a setting.** Gemini 3.5 Flash-Lite can think before it answers, at four levels: `minimal`
(its default), `low`, `medium` and `high`. The thinking happens before the visible answer and isn't shown, but it's
counted: `usage_metadata["output_token_details"]["reasoning"]` holds the thinking tokens, and they're included in
the output tokens you pay for (project 11). On Gemini 3 and later models, `thinking_level` replaces the older
`thinking_budget`, a number of tokens.

The thinking tokens count towards `max_output_tokens` too, which is why this project sets it to 2,000: with a small
cap, the model could use it all on thinking and be cut off before the answer.

### ③ One chain per way

```python
# ③ One chain per way. bind(thinking_level=...) changes the setting for that chain only.
def make_chain(way: dict):
    prompt = ChatPromptTemplate.from_messages([("system", way["system"]), ("human", "{question}")])
    step = model.bind(thinking_level=way["thinking_level"]) if way["thinking_level"] else model
    return prompt | step                     # no parser: the token counts are in the AIMessage


chains = {name: make_chain(way) for name, way in WAYS.items()}
```

- `model.bind(thinking_level="high")` wraps the model: every call made through this chain carries
  `thinking_level="high"`, and `model` itself is unchanged, as with `bind(max_output_tokens=...)` in project 11. Only
  the thinking chain gets it; the other two use `model` as it is.
- `x if condition else y` is Python's version of Java's `condition ? x : y`.
- There's no `StrOutputParser`: as in project 11, the chain gives back the whole `AIMessage`, because the token
  counts are in it.
- `chains` is a dict with one chain per way: `{"direct": ..., "step_by_step": ..., "thinking": ...}`.

### ④ Reading the answer

```python
def read_answer(text: str) -> float | None:
    """The number on the last "Answer:" line, or None if there isn't one. "Answer: 1,250" -> 1250.0"""
    plain = text.replace("*", "")            # Markdown bold: "**Answer:** 5" and "Answer: **5**" mean "Answer: 5"
    found = re.findall(r"Answer:\s*[₹$]?\s*(-?[\d,]*\.?\d+)", plain)
    return float(found[-1].replace(",", "")) if found else None
```

Every way ends with the same `Answer:` line, so one function can check all three:

- A model may write the line in Markdown bold (`**Answer:** 5`), so the stars are taken out first.
- The pattern, piece by piece: `Answer:` is the label; `\s*` allows any spaces; `[₹$]?` allows one rupee or dollar
  sign; `-?[\d,]*\.?\d+` is the number, with an optional minus, commas and decimal point. The brackets around the
  number keep just that part.
- `re.findall()` returns every match, and `[-1]` takes the last one: a model that checks its work may write more
  than one `Answer:` line.
- `float()` turns `"1250"` into `1250.0`, and `5.0 == 5` is true, so it compares with the whole-number answers.
- No `Answer:` line gives `None`, which counts as wrong: code that relies on the answer couldn't use it either.

`report()` turns one reply into one cell of the table:

```python
def report(message: AIMessage, expected: float, latency_ms: int) -> dict:
    """One answer, as a cell of the table: its text, the number read from it, right or wrong, tokens and time."""
    value = read_answer(message.text)
    usage = message.usage_metadata or {}
    return {
        "text": message.text,
        "value": value,
        "correct": value == expected,
        "output_tokens": usage.get("output_tokens", 0),            # the visible answer plus any thinking
        "thinking_tokens": usage.get("output_token_details", {}).get("reasoning", 0),   # missing when it's 0
        "latency_ms": latency_ms,
    }
```

`message.text` is the reply's text (project 11). A reply that carries no counts has `usage_metadata` set to `None`,
and `or {}` swaps that for an empty dict, so the `.get()` calls still work. Gemini leaves out the `reasoning` count
when there was no thinking, so `.get(..., 0)` gives 0 instead of an error.

### ⑤ 18 calls, 4 at a time

```python
async def ask(way: str, item: dict, limit: asyncio.Semaphore) -> dict:
    """One question, one way, timed. Any failure comes back as an error for that one cell."""
    async with limit:                        # wait here if AT_ONCE calls are already running
        try:
            start = time.perf_counter()      # the clock starts once the call is let in: waiting isn't counted
            message = await chains[way].ainvoke({"question": item["question"]})
            return report(message, item["answer"], round((time.perf_counter() - start) * 1000))
        except Exception as err:
            return {"error": f"Gemini didn't answer ({type(err).__name__}).", "detail": str(err)}


async def ask_every_way(item: dict, limit: asyncio.Semaphore) -> dict:
    """One question, all three ways: one row of the table."""
    # The * hands gather() each call as its own argument. dict(zip(...)) pairs each way's name with its cell.
    cells = await asyncio.gather(*(ask(way, item, limit) for way in WAYS))
    return {"question": item["question"], "expected": item["answer"], "ways": dict(zip(WAYS, cells))}


async def compare() -> list[dict]:
    """Every question, every way: 6 x 3 = 18 calls, at most AT_ONCE at a time."""
    limit = asyncio.Semaphore(AT_ONCE)       # one set of permits, shared by all 18 calls
    # Every row starts at once; the rows come back in the order of QUESTIONS.
    return await asyncio.gather(*(ask_every_way(item, limit) for item in QUESTIONS))
```

This is the first `hello.py` with its own async functions. In order:

1. **`async def` and `await`**: project 2 awaited `chain.ainvoke(...)` inside an `async def` route. `ask()` is the
   same idea in our own code: while one call waits for Gemini, the others can run.
2. **`asyncio.gather(a, b, c)`** runs them all at the same time and waits for all of them. The results come back in
   the order you passed them in, whichever finishes first, so the rows follow `QUESTIONS` and the cells follow `WAYS`.
3. **`asyncio.Semaphore(AT_ONCE)`** is a counter of 4 permits, shared by all 18 calls. `async with limit:` takes one,
   waiting if none is free, and gives it back at the end of the block. Java's `java.util.concurrent.Semaphore` works
   the same way.
4. **The clock starts inside the block**, so the time a call spends waiting for a permit isn't counted in its cell.
5. **A failure stays in its own cell**: `{"error": ..., "detail": ...}`, and the other calls still come back.
6. **`asyncio.run(compare())`** is how the script runs it. In `main.py`, FastAPI already runs the async code for its
   routes, so the route just writes `await hello.compare()`.

Why not `batch(config={"max_concurrency": ...})` as in projects 7 and 14? It runs one chain over a list of inputs.
Here three different chains share one cap, and each call gets its own timer and its own error.

**The free tier.** **Run all** makes 18 calls, at most 4 at a time (`AT_ONCE`); `python hello.py` makes 20 (the 18,
then the two prompts). Four at a time keeps the burst small, but it doesn't cap calls per minute: 18 quick calls can
still go over the free tier's per-minute limit. When that happens Gemini answers 429, and the library waits and tries
again by itself, up to 5 more times, about 1, 2, 4, 8 and 16 seconds apart. So the first sign is slower calls, and the
waiting is counted in that cell's time. Only a call that still fails after the last try shows
`Gemini didn't answer (...)`; the other cells still come back.

### The summary per way

```python
def summary(rows: list[dict]) -> dict:
    """Per way: how many were right, and the average tokens and time of the calls that answered."""
    result = {}
    for way in WAYS:
        cells = [row["ways"][way] for row in rows if "error" not in row["ways"][way]]
        count = len(cells) or 1                  # "or 1": no dividing by zero when every call failed
        result[way] = {
            "correct": sum(cell["correct"] for cell in cells),         # True counts as 1, False as 0
            "answered": len(cells),
            "avg_output_tokens": round(sum(cell["output_tokens"] for cell in cells) / count),
            "avg_thinking_tokens": round(sum(cell["thinking_tokens"] for cell in cells) / count),
            "avg_latency_ms": round(sum(cell["latency_ms"] for cell in cells) / count),
        }
    return result
```

`summary()` counts the right answers per way and averages the tokens and time of the calls that answered; a failed
call is left out, not counted as zero. In Python, `True` adds up as 1, so `sum()` over the `correct` values counts
the right answers.

What to look for in your table:

- **Accuracy:** do the traps (the bat and ball, the machines) catch `direct`? A model that answers at once may fall
  for them, or get all six right. Run it a few times.
- **Tokens:** `step_by_step` writes its steps out, so it should use many more output tokens than `direct`.
  `thinking` should write a short answer but have a large thinking count.
- **Time:** more tokens take longer. A call that was retried also counts its waiting, so one slow cell can be the
  free tier, not the reasoning.
- **The trade-off:** for an easy question, reasoning is wasted money and time. For a hard one, it can be the
  difference between right and wrong. Pick it per task.

### ⑥ A prompt, before and after

```python
BEFORE_PROMPT = (
    "Look at this message from a customer and tell me about it. Keep it short but explain everything in detail, "
    "and write them a reply too.\n\n{message}"
)
# The fixed one puts the rules in the system message, and the customer's words, labelled, in the human message,
# kept apart from the rules (project 13).
AFTER_SYSTEM = (
    "You read customer support messages for an online shop. "
    'Say what the customer wants, in one sentence of at most 20 words, starting with "The customer wants". '
    "Do not write a reply."
)
AFTER_PROMPT = "Customer message:\n{message}"
```

| Mistake | Before | After |
|---|---|---|
| A vague goal | "tell me about it" | "say what the customer wants" |
| Instructions that conflict | "keep it short but explain everything in detail" | "one sentence of at most 20 words" |
| No output format | none: any shape will do | "starting with 'The customer wants'" |
| Several tasks in one request | "tell me about it ... and write them a reply too" | one task, and "Do not write a reply" |

The "before" prompt is one human message with the customer's text pasted at the end. Besides fixing the four
mistakes, the "after" prompt puts its rules in the system message, and the customer's words, labelled
`Customer message:`, in the human message, as in project 13. Both chains end in a `StrOutputParser`: here only the
text matters.

Click **Try both prompts** to see the difference: the "before" answer can come back in a different shape and length
each time, while the "after" one is asked for a single sentence that code could store or show. To write a reply as
well, make it a second request, with its own clear prompt.

### The server and the page

- `GET /api/setup` returns the questions, the ways, both prompts, the anti-patterns and the sample message. The page
  builds its tables from them, so it always shows what the code really sends.
- `POST /api/compare` awaits `hello.compare()` and answers 200 even when some calls failed. It takes each failure's
  full reason out of its cell and logs it in the server's terminal, so the page only learns the error type:

  ```python
  @app.post("/api/compare")
  async def compare():
      """Every question, three ways. The full reason for any failed call goes to this terminal, not the page."""
      rows = await hello.compare()
      for row in rows:
          for way, cell in row["ways"].items():
              if "error" in cell:
                  detail = cell.pop("detail")          # take the full reason out: the page gets only the error type
                  logger.warning("Gemini call failed (%s): %s", way, detail)
      return {"rows": rows, "summary": hello.summary(rows)}
  ```

  The page counts the error cells, and says `Done, but Gemini didn't answer 3 of the 18 calls: the server's terminal
  says why.` when there are any.
- `POST /api/fix` checks the message first (`FixIn`: 1 to 1,000 characters, spaces trimmed), so a bad one gets a 422
  and costs nothing. Then it runs both chains at the same time with `asyncio.gather`. If either fails, the answer is
  a 502, `Gemini didn't answer (TypeName).`, and the full reason goes to the server's terminal.

## Run it

```bash
cd tutorials/16-gemini-reasoning
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the `.env` from [Before you start](#before-you-start) in place:

```bash
python config.py                     # GOOGLE_API_KEY is set.   (the key itself is never printed)
python hello.py                      # 20 calls: the six questions three ways, the summary, then the prompt before/after
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

Or try it with curl. These are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl http://127.0.0.1:8000/api/setup
curl -X POST http://127.0.0.1:8000/api/compare          # 18 calls: it takes a while
curl -X POST http://127.0.0.1:8000/api/fix -H "Content-Type: application/json" \
     -d '{"message": "my parcel says delivered but nothing came, and i need it for a birthday tomorrow"}'
```

## Test it

The plain tests make no call to Gemini, so they're free and need no key. They check:

- `read_answer()` on ten texts: plain and Markdown-bold `Answer:` lines, commas, a ₹ sign, the last of two
  `Answer:` lines, and no `Answer:` line at all
- the questions and the ways: six questions with whole-number answers, `direct` and `thinking` share a prompt,
  `step_by_step` asks for steps, every way asks for the `Answer:` line, only the thinking chain binds
  `thinking_level="high"`, and the model with its 2,000-token cap
- `report()` and `summary()`, including a summary where a call failed
- `compare()` with stand-in chains instead of Gemini: the rows come back in order, no more than `AT_ONCE` calls run
  at once, and a failed call becomes an error in its own cell
- the two prompts: the four mistakes before, and their fixes after
- `python hello.py` without a key stops with the message, not a traceback
- the endpoints: `/api/setup`; `/api/compare` keeps the full reason off the page and puts it in the server's log;
  `/api/fix` runs both prompts, answers 422 for an empty message and 502 when a call fails
- the page, at `/` and `/index.html`, holds no key

The live tests make 4 real calls. They ask the bat-and-ball question three ways (every answer has an `Answer:` line,
`step_by_step` writes more output tokens than `direct`, and `thinking` reports thinking tokens), and check that the
fixed prompt gives one short sentence starting with "The customer wants".

That's **29 plain tests and 2 live ones**. Without a key, `tests/conftest.py` skips the live ones, and pytest says
`29 passed, 2 skipped`.

```bash
python -m pytest                     # every test; the live ones run only when there's a key
python -m pytest -m "not live"       # only the plain ones: no call, no cost
python -m pytest -m live             # only the live ones: 4 real calls to Gemini
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No key | `python hello.py` stops with `Can't build the chain: GOOGLE_API_KEY is not set ...` | Copy the `.env` from project 9 (see [Before you start](#before-you-start)) |
| A wrong key | Every cell says `Gemini didn't answer (GoogleInvalidRequestError).` The server's terminal says why (`API key not valid`). `python hello.py` prints the same reason on each line, then stops with a traceback from the prompt before/after, which has no `try` | Fix the key in `.env` |
| The free tier's per-minute limit | Slower calls while the library tries again. If every try fails, `Gemini didn't answer (...)` in those cells, and the page says how many | Wait a minute and run it again, or lower `AT_ONCE` |
| The thinking used up the cap | `✘ no answer line` in a cell, with about 2,000 output tokens | Raise `MAX_OUTPUT_TOKENS` |
| An answer without an `Answer:` line | `✘ no answer line`, counted as wrong | Open "the answer" to read it: code couldn't use it either |
| An empty or too-long customer message | A 422 and no call. The page shows `message: String should have at least 1 character` (or `at most 1000 characters`) | Type 1 to 1,000 characters |
| Gemini fails on **Try both prompts** | A 502. The page shows `Gemini didn't answer (...). The server's terminal says why.` | Read the reason in the server's terminal |

## Things to try

Each change makes one or two tests fail: they pin today's settings. That's expected; update the test if you keep the
change.

1. **Turn the thinking down.** In `WAYS`, set the thinking way's `"thinking_level"` to `"low"` and run
   `python hello.py`. The thinking way should show fewer thinking tokens and less time; see whether it still gets the
   traps right. `test_direct_and_thinking_share_a_prompt_and_differ_only_in_thinking` and
   `test_only_the_thinking_chain_turns_thinking_up` fail: they guard the setting.
2. **Squeeze the cap.** Set `MAX_OUTPUT_TOKENS = 200`. A thinking cell may now come back `✘ no answer line`, with
   output tokens near 200: the thinking used the room before the answer was written. `test_model_settings` fails.
3. **One call at a time.** Set `AT_ONCE = 1` and click **Run all**. The whole run takes several times as long, but
   each cell's own time stays about the same, because the clock starts only once a call is let in.
   `test_compare_never_runs_more_than_at_once_calls` fails.
4. **Add your own trap.** Add
   `{"question": "A farmer has 17 sheep. All but 9 run away. How many sheep are left?", "answer": 9},` to
   `QUESTIONS`. The page now says `7 questions × 3 ways = 21 calls.` Does `direct` answer 8?
   `test_every_question_has_a_whole_number_answer` fails until you change its 6 to 7.

## Next

**[Project 17 · Prompts as versioned files](../17-gemini-prompt-files/README.md)**: the greeting prompt moves out of
the code into files, one per version, and every answer says which version produced it.
