# 11 · Tokens and cost

The same Gemini welcome as project 10, plus the numbers behind each call: how many tokens went in and came out,
how long it took, and what it would cost. A **max output tokens** box lets you cap the answer and watch it get cut
off.

```text
max 200  ->  "Welcome, Asha! LangChain is a great place to start."   STOP        in 21 · out 27 · 640 ms · $0.0000738
max 10   ->  "Welcome, Asha! LangChain"                              MAX_TOKENS  in 21 · out 10 · 610 ms · $0.0000313
             (made-up numbers: the real ones change from call to call)
```

## What you learn

- **Tokens** are the pieces of text a model reads and writes: a short word is often one token, a long word
  several. You pay per token, and the **context window** (how much the model can read at once) is measured in them
- **Counting before the call:** `model.get_num_tokens(text)`, Gemini's free `count_tokens`
- **Reading the bill after the call:** `message.usage_metadata`, the input and output tokens Gemini actually counted
- **The price of one call**, worked out from those numbers: output tokens cost more than input tokens
- **`max_output_tokens`** caps each answer: a lower cap means a shorter answer and a smaller bill
- **Latency:** how long one call takes
- **Temperature**, and why this project doesn't have a slider for it (see below)

## Before you start: the key

As in project 10, copy your `.env` across (or use a Codespaces secret):

```bash
cd projects/11-gemini-tokens
cp ../10-gemini-llm/.env .env
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `hello.py` | `ask(name, max_output_tokens)`: counts the prompt's tokens, calls Gemini, times it, and returns the answer with its numbers. `estimate_cost()` and `usage_report()` are plain functions with no call. `python hello.py Asha 10` tries it |
| `config.py` | Loads and checks the key: the same file as projects 9 and 10 |
| `main.py` | FastAPI: `POST /api/hello` with `{"name", "max_output_tokens"}` (10 to 200) returns the report. A bad request gets a 422 before any call; a failed call gets a 502 |
| `index.html` | The page: a name, a max-tokens box, and a table with one row per call, newest first, plus the total cost |
| `tests/conftest.py` | Skips the live tests when there is no key, as in project 10 |
| `tests/test_hello.py` | 17 plain tests (no call) and 2 live tests (two real calls) |
| `requirements.txt` | The same as project 10 |

## One call, measured

```python
def ask(name, max_output_tokens=200):
    counted_tokens = model.get_num_tokens(prompt.format(name=name))      # ① before: count the prompt (free)

    start = time.perf_counter()
    message = (prompt | model.bind(max_output_tokens=max_output_tokens)).invoke({"name": name})   # ② the call
    latency_ms = round((time.perf_counter() - start) * 1000)

    return usage_report(message, counted_tokens, latency_ms)               # ③ read the numbers out of the reply
```

- **No `StrOutputParser` this time.** The parser would keep only the text, and the numbers are in the rest of the
  `AIMessage`: `message.usage_metadata` holds the tokens, and `message.response_metadata` holds the finish reason.
- **`model.bind(max_output_tokens=...)`** makes a copy of the model step with one setting changed, for this call
  only. The `model` itself keeps its cap of 200.
- **`count_tokens` is a second, small request** to Google. It's free and doesn't touch the main call. It tells
  you the size before you send, which is how you'd check that a long document fits.

## What the numbers mean

| Column | From | Meaning |
|---|---|---|
| Counted before | `get_num_tokens()` | Tokens in the prompt, counted before the call |
| Input | `usage_metadata["input_tokens"]` | Tokens Gemini says it read. Compare it with "counted before": it may differ by a few, because the call wraps the prompt as a message |
| Output | `usage_metadata["output_tokens"]` | Tokens it wrote, **including thinking tokens** |
| Thinking | `usage_metadata["output_token_details"]["reasoning"]` | Tokens the model spent thinking before it answered. Small or 0 for this model, whose default is minimal thinking |
| Finish | `response_metadata["finish_reason"]` | `STOP`: it finished. `MAX_TOKENS`: it hit the cap and was cut off mid-sentence |
| Time | `time.perf_counter()` around the call | How long the call took, in milliseconds |
| Cost | `estimate_cost(input, output)` | The price of this call on the paid tier |

## What it costs

```python
PRICE_PER_MILLION_INPUT = 0.30     # US dollars per 1 million input tokens, gemini-3.5-flash-lite, paid tier
PRICE_PER_MILLION_OUTPUT = 2.50    # per 1 million output tokens (thinking included)

cost = (input_tokens * 0.30 + output_tokens * 2.50) / 1_000_000
     = (21 * 0.30 + 27 * 2.50) / 1_000_000 = $0.0000738        # one welcome: about 1/135 of a cent
```

- These are Google's prices from the [Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing),
  checked on 2026-10-17. Prices change, so check that page before you rely on them.
- **On the free tier, these calls cost nothing.** The page shows what they *would* cost on the paid tier.
- **An output token costs about 8 times an input token** ($2.50 against $0.30). A long answer costs much more than
  a long question, which is why `max_output_tokens` is the first thing to cap.
- 10,000 welcomes like this one would cost about $0.74. Bigger prompts, like whole documents (later projects),
  are where token counts start to matter.

## What about temperature?

**Temperature** is the setting that controls how random a model's choice of words is. Low means predictable, and
high means more varied. The roadmap planned a temperature slider here, comparing 0 with 1.

Google has since **deprecated** temperature, along with `top_p` and `top_k`. For Gemini 3.5 Flash-Lite, Gemini 3.6
Flash and later models, the API says these parameters are "deprecated and ignored", and future models will reject
them with an error ([what's new in Gemini 3.6 Flash and 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6)).
`langchain-google-genai` drops them from the request and warns:

```text
UserWarning: Model 'gemini-3.5-flash-lite' uses fixed sampling defaults; the sampling parameter(s) temperature will be ignored.
```

A slider would change nothing, so this project doesn't have one. What you can still see:

- **The answers vary.** Click **Ask Gemini** three times with the same name: three different welcomes. The model
  picks its words with some randomness, and on these models you can't turn that off.
- **To make answers more consistent**, Google's advice is to write clear rules in the instructions: a system prompt
  (a later project) and examples (the few-shot project).
- **`max_output_tokens` is the setting that matters for cost**, so that's the box on this page.

## Run it

```bash
cd projects/11-gemini-tokens
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../10-gemini-llm/.env .env      # the key, once (see above)

python hello.py                    # one call for Raghu, and its numbers
python hello.py Asha 10            # at most 10 output tokens: cut off, finish_reason MAX_TOKENS
python -m pytest                   # 19 tests: 17 plain, 2 live
python -m pytest -m "not live"     # only the plain ones: no call, no cost

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"name": "Asha", "max_output_tokens": 10}'
```

Each click makes two requests to Google: the free token count, and the call itself.

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Make the page feel faster: stream the answer word by word as Gemini writes it, instead of waiting for all of it.
