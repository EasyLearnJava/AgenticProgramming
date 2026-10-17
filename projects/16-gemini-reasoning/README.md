# 16 · Reasoning: chain-of-thought and thinking

Some questions need a few steps, and a model that answers straight away can get them wrong, just as a person can.
This project asks the same six multi-step questions three ways and measures each way: how many it gets right, how
many tokens it uses, and how long it takes. A second part takes one badly written prompt and fixes its mistakes.

```text
                 right    avg output tokens    avg thinking tokens    avg time
direct           4 of 6          5                    0                 500 ms
step_by_step     6 of 6        150                    0                1800 ms
thinking         6 of 6        420                  410                2600 ms
                 (made-up numbers: run it to see yours)
```

## What you learn

- **Chain-of-thought**: asking the model, in the prompt, to work through the steps before it answers
- **Thinking**: a setting that makes the model reason privately before it writes its answer (`thinking_level`)
- **What reasoning costs**: more output tokens and more time, which a table makes visible
- **Checking answers in code**: every answer ends with `Answer: <number>`, and `read_answer()` compares it
- **Four prompt anti-patterns**, and how to fix them

## Before you start: the key

As in project 10, copy your `.env` across (or use a Codespaces secret):

```bash
cd projects/16-gemini-reasoning
cp ../10-gemini-llm/.env .env
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `hello.py` | The six `QUESTIONS`, the three `WAYS`, `read_answer()`, `compare()` and `summary()`; then the prompt before and after. `python hello.py` runs everything and prints the tables |
| `config.py` | Loads and checks the key: the same file as projects 9 to 15 |
| `main.py` | FastAPI: `POST /api/compare` runs the 18 calls, `POST /api/fix` tries both prompts, `GET /api/setup` gives the page what to show |
| `index.html` | The page: the three ways, a summary table, a row per question (open "the answer" to read it), and the before/after |
| `tests/conftest.py` | Skips the live tests when there is no key |
| `tests/test_hello.py` | 26 plain tests (no call) and 2 live tests (four real calls) |
| `requirements.txt` | The same as project 10 |

## The questions

Six word problems, each with one right number. Several are well-known traps, where the first answer that comes to
mind is wrong:

| Question (short) | The quick answer | The right answer |
|---|---|---|
| A bat and a ball cost 110; the bat costs 100 more. The ball? | 10 | **5** (ball 5 + bat 105 = 110) |
| 3 boxes of 12 apples, give away a third, buy 7 | | **31** |
| 5 machines make 5 widgets in 5 minutes; 100 machines, 100 widgets? | 100 | **5** |
| Lily pads double daily and cover the lake on day 48; half? | 24 | **47** |
| 800, cut by 25%, then up by 10% | 680 | **660** |
| 15 pages Monday, 5 more each day; total by Friday? | | **125** |

## The three ways

```python
WAYS = {
    "direct":       {"system": "... Reply with only the answer. End with one line ... 'Answer: <number>' ...",
                     "thinking_level": None},
    "step_by_step": {"system": "... Work through the problem step by step, writing each step on its own line, "
                               "then check your result. End with one line ... 'Answer: <number>' ...",
                     "thinking_level": None},
    "thinking":     {"system": "... Reply with only the answer. End with one line ... 'Answer: <number>' ...",
                     "thinking_level": "high"},
}
```

| Way | What changes | Where the reasoning goes |
|---|---|---|
| `direct` | nothing: answer at once | nowhere |
| `step_by_step` | the **prompt** asks for steps | into the answer you can read, as visible text |
| `thinking` | the **setting** `thinking_level="high"`; the prompt is the same as `direct` | into hidden thinking tokens you don't see, but do pay for |

`direct` and `thinking` have exactly the same prompt, so any difference between them comes from the setting.

### Chain-of-thought: reasoning in the prompt

A model writes one token after another, and each token can only build on what's already written. Asking for steps
first gives it room: the working-out is written before the answer, so the answer can build on it. Those steps are
ordinary output: you can read them, and they cost output tokens.

### Thinking: reasoning as a setting

```python
model.bind(thinking_level="high")
```

Gemini 3.5 Flash-Lite can think before it answers, at four levels: `minimal` (its default), `low`, `medium` and
`high`. The thinking happens before the visible answer and isn't shown, but it's counted:
`usage_metadata["output_token_details"]["reasoning"]` holds the thinking tokens, and they're included in the output
tokens you pay for (project 11). On Gemini 3 and later models, `thinking_level` replaces the older
`thinking_budget`, a number of tokens.

The thinking tokens count towards `max_output_tokens` too, which is why this project sets it to 2,000: with a
small cap, the model could use it all on thinking and be cut off before the answer.

### Checking the answer

```python
def read_answer(text):            # "Step 1 ... Step 3: 24 + 7 = 31.\nAnswer: 31"  ->  31.0
    found = re.findall(r"Answer:\s*[₹$]?\s*(-?[\d,]*\.?\d+)", text)
    return float(found[-1].replace(",", "")) if found else None
```

Every way ends with the same `Answer:` line, so one function can check all three. An answer with no `Answer:` line
counts as wrong: code that relies on the answer couldn't use it either.

## What to look for in your table

- **Accuracy:** do the traps (the bat and ball, the machines) catch `direct`? With a small, fast model they
  sometimes do; on another day it might get all six. Run it a few times.
- **Tokens:** `step_by_step` writes its steps out, so it uses many more output tokens than `direct`. `thinking`
  writes a short answer but has a large thinking count.
- **Time:** more tokens take longer.
- **The trade-off:** for an easy question, reasoning is wasted money and time. For a hard one, it can be the
  difference between right and wrong. Pick it per task.

## A prompt, before and after

```text
Before:  Look at this message from a customer and tell me about it. Keep it short but explain everything in
         detail, and write them a reply too.

After:   system: You read customer support messages for an online shop.
         human:  Say what the customer wants, in one sentence of at most 20 words, starting with "The customer
                 wants". Do not write a reply.

                 Customer message:
                 {message}
```

| Mistake | Before | After |
|---|---|---|
| A vague goal | "tell me about it" | "say what the customer wants" |
| Instructions that conflict | "keep it short but explain everything in detail" | "one sentence of at most 20 words" |
| No output format | none: any shape will do | "starting with 'The customer wants'" |
| Several tasks in one request | "tell me about it ... and write them a reply too" | one task, and "Do not write a reply" |

The "after" prompt also labels the customer's text (`Customer message:`) and keeps the instructions in the system
message, as in project 13. Click **Try both prompts** to see the difference: the "before" answer can come back
in a different shape and length each time, while the "after" one is asked for a single sentence that code could
store or show.

To write a reply as well, make it a second request, with its own clear prompt.

## The free tier and 18 calls

**Run all** makes 18 calls, at most 4 at a time (`AT_ONCE`). If the free tier's per-minute limit is hit, those
cells show `Gemini didn't answer (...)` and the rest still come back. Wait a minute and run it again.

## Run it

```bash
cd projects/16-gemini-reasoning
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../10-gemini-llm/.env .env      # the key, once (see above)

python hello.py                    # the three ways for all six questions, the summary, then the prompt before/after
python -m pytest                   # 28 tests: 26 plain, 2 live
python -m pytest -m "not live"     # only the plain ones: no call, no cost

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Prompts as versioned files: move every prompt out of the code, and record which version produced each answer.
