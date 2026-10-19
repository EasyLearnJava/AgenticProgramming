# 11 · Tokens and cost

This project makes the same Gemini welcome as project 10 and shows the numbers behind each call: the tokens in and
out (what you pay for), how long it took, and what it would cost. A **max output tokens** box caps the answer, so you
can watch it get cut off and cost less.

```text
max 200  ->  "Welcome, Asha! LangChain is a great place to start."   STOP        in 21 · out 27 · 640 ms · $0.0000738
max 10   ->  "Welcome, Asha! LangChain"                              MAX_TOKENS  in 21 · out 10 · 610 ms · $0.0000313
             (made-up example: Gemini's words and numbers change every time)
```

## What you'll build

- **`hello.py`**, with `ask(name, max_output_tokens)`: one measured call. It counts the prompt's tokens, calls Gemini
  with that cap, times the call and prices it. `python hello.py Asha 10` prints the answer and its numbers, with
  `finish_reason: MAX_TOKENS` when the cap cuts it off.
- **`POST /api/hello`**: send `{"name": "Asha", "max_output_tokens": 10}` (10 to 200) and get the same numbers back as
  JSON. A bad request gets a 422 before anything reaches Google; a failed call gets a 502.
- **A page** with a name box, a max-tokens box and a table with one row per call, newest first: the answer, why it
  stopped, the token counts, the time and the cost, plus the running total.

## What you'll learn

- **Tokens**: the pieces of text a model reads and writes. A short word is often one token, a long word several. You
  pay per token, and the **context window** (how much the model can read at once) is measured in them.
- **`model.get_num_tokens(text)`**: counting a prompt before you send it, with Gemini's free `count_tokens` request.
- **`usage_metadata` and `response_metadata`**: the tokens Gemini counted (output includes thinking) and why it
  stopped (`STOP` or `MAX_TOKENS`).
- **`model.bind(max_output_tokens=...)`**: a setting for one call that leaves the model itself unchanged.
- **Latency and cost**: timing a call with `time.perf_counter()`, and pricing it from per-million-token rates. Output
  costs about 8 times as much as input.
- **Why there's no temperature setting**: on this model it is deprecated and ignored.

## What's new since project 10

Compared with [Project 10 · First real LLM call](../10-gemini-llm/README.md):

- **No `StrOutputParser`.** The chain stops at the model, so you get the whole `AIMessage` and read `message.text`,
  `usage_metadata` and `response_metadata` yourself.
- **One function around the call, `ask()`**: a free token count before it, a stopwatch around it and a price after it.
- **A cap for each call.** Project 10 gave every call the same cap of 200. Now `chain_for(n)` binds
  `max_output_tokens=n` to the model for one call, and Pydantic checks it is 10 to 200 (`ge=10, le=MAX_OUTPUT_TOKENS`,
  the first number limits in these projects).
- **The endpoint is a plain `def` that calls `ask()`**, where project 10's was `async def` with `chain.ainvoke()`. The
  tests swap out `main.ask` instead of `main.chain`.

## Before you start

- **Python 3.11 or newer.**
- **Your Gemini key** from [project 9](../09-gemini-key/README.md), copied into this folder once with
  `cp ../09-gemini-key/.env .env` (run it in `tutorials/11-gemini-tokens`). In GitHub Codespaces you can use a
  Codespaces secret named `GOOGLE_API_KEY` instead, which every project sees.

## Files

| File | What it is |
|---|---|
| `hello.py` | The prompt and the model, `chain_for()`, `estimate_cost()`, `dollars()`, `usage_report()`, and `ask()`, which makes one measured call. `python hello.py Asha 10` runs it |
| `main.py` | FastAPI: `GET /` and `/index.html` serve the page; `POST /api/hello` runs `ask()` and returns its numbers. A bad request gets a 422 before any call; a failed call gets a 502 |
| `index.html` | The page: a name box, a max-tokens box, and a table with one row per call, newest first, plus the total cost |
| `config.py` | Loads and checks the key: the same file as project 9 |
| `.env.example` | The template for `.env`, the file that holds your key. `.env` is in `.gitignore`, so it never goes into git |
| `tests/test_hello.py` | The plain tests (no call) and the live tests (real calls to Gemini) |
| `tests/conftest.py` | Checks once for a real key: with none, it gives `hello.py` a fake one and skips the live tests |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, looks only in `tests/`, and defines the `live` marker |
| `requirements.txt` | `fastapi`, `uvicorn`, `langchain-core`, `langchain-google-genai`, `google-genai`, `python-dotenv`: the same as project 10 |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |
| `README.md` | This page |

## How it works

### The prompt and the model, with no parser

```python
# The same prompt and model as project 10.
prompt = PromptTemplate.from_template(
    "Write a short, friendly welcome for {name}, who is starting to learn LangChain. One or two sentences."
)
model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)
```

`MODEL` is `"gemini-3.5-flash-lite"` and `MAX_OUTPUT_TOKENS` is 200, as before. What's gone is project 10's
`StrOutputParser`: it kept only the text, and the numbers are in the rest of the `AIMessage`.

### One call, measured: `ask()`

```python
def ask(name: str, max_output_tokens: int = MAX_OUTPUT_TOKENS) -> dict:
    """One call, measured: count the prompt, call Gemini with this call's cap, time it, and read the numbers."""
    # ① Before: count the prompt's tokens. This is its own small request to Google (count_tokens), and it's free.
    counted_tokens = model.get_num_tokens(prompt.format(name=name))

    # ② The call itself, timed. perf_counter() is a stopwatch: only the difference between two readings matters.
    start = time.perf_counter()
    message = chain_for(max_output_tokens).invoke({"name": name})
    latency_ms = round((time.perf_counter() - start) * 1000)

    # ③ After: read the tokens, the finish reason and the cost out of the reply.
    return usage_report(message, counted_tokens, latency_ms)
```

`main.py` calls this once per request, and `python hello.py` calls it once per run.

### ① Count the prompt before the call

`model.get_num_tokens(...)` sends the filled-in prompt to Gemini's `count_tokens`: its own small request to
Google. It's free and doesn't touch the main call. It tells you the size before you send, which is how you'd check
that a long document fits in the context window.

### ② The call, capped and timed

The chain for this one call comes from `chain_for()`:

```python
# The chain for one call: the prompt, then the model with this call's cap. No StrOutputParser this time: we want the
# whole AIMessage, because the token counts are in it.
# bind() wraps the model: every call made through the wrapper carries max_output_tokens, and `model` itself keeps its
# cap of 200. Bind the model, not the chain: (prompt | model).bind(...) hands the setting to the chain's first step,
# the prompt, which ignores it, so the cap is lost without any error.
def chain_for(max_output_tokens: int):
    return prompt | model.bind(max_output_tokens=max_output_tokens)
```

- **`model.bind(max_output_tokens=...)` wraps the model** rather than copying it: `chain_for(10).last.bound is model`
  is `True`. Calls made through the wrapper carry the cap; the `model` object itself is unchanged.
- **Bind the model, not the chain.** `(prompt | model).bind(max_output_tokens=10)` looks the same, but a chain hands
  call settings only to its first step. The request still asks for 200, and nothing warns you.
- **`time.perf_counter()`** is Python's stopwatch, like Java's `System.nanoTime()` but in seconds: one reading means
  nothing, the difference between two does. The time covers only the model call, not the count before it.

### ③ Read the numbers out of the reply

`usage_report()` reads everything worth showing out of the `AIMessage`:

```python
def usage_report(message: AIMessage, counted_tokens: int, latency_ms: int) -> dict:
    usage = message.usage_metadata                                  # filled in by Gemini, for every call
    return {
        # .text, not .content: this model's content is a list of blocks, and .text joins their text
        # (project 10's StrOutputParser did that for us).
        "answer": message.text,
        "finish_reason": message.response_metadata.get("finish_reason"),   # "STOP" = done, "MAX_TOKENS" = cut off
        "counted_tokens": counted_tokens,                           # counted before the call
        "input_tokens": usage["input_tokens"],                      # what Gemini says it read
        "output_tokens": usage["output_tokens"],                    # what it wrote, thinking included
        # output_token_details is there only when the model spent tokens thinking, so 0 when it's missing.
        "thinking_tokens": usage.get("output_token_details", {}).get("reasoning", 0),
        "latency_ms": latency_ms,
        "cost_usd": estimate_cost(usage["input_tokens"], usage["output_tokens"]),
    }
```

A reply's `usage_metadata` looks like this (made-up numbers):

```text
{'input_tokens': 21, 'output_tokens': 27, 'total_tokens': 48, 'input_token_details': {'cache_read': 0}}
```

| Column on the page | From | Meaning |
|---|---|---|
| Counted before | `get_num_tokens()` | Tokens in the prompt, counted before the call |
| Input | `usage_metadata["input_tokens"]` | Tokens Gemini says it read. Both requests carry the same prompt text, so compare it with "Counted before". The cost uses this one |
| Output | `usage_metadata["output_tokens"]` | Tokens it wrote, **including thinking tokens** |
| Thinking | `usage_metadata["output_token_details"]["reasoning"]` | Tokens the model spent thinking before it answered. Small or 0 for this model, whose default is minimal thinking |
| Finish | `response_metadata["finish_reason"]` | `STOP`: it finished. `MAX_TOKENS`: it hit the cap and was cut off mid-sentence |
| Time (ms) | `time.perf_counter()` around the call | How long the call took, in milliseconds |
| Cost (USD) | `estimate_cost(input, output)` | The price of this call on the paid tier |

### What it costs

```python
PRICE_PER_MILLION_INPUT = 0.30
PRICE_PER_MILLION_OUTPUT = 2.50
...
# The price of one call: tokens times the price per token. Input and output have different prices; output costs more.
def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_PER_MILLION_INPUT + output_tokens * PRICE_PER_MILLION_OUTPUT) / 1_000_000
```

For the welcome at the top of this page:

```text
cost = (21 × 0.30 + 27 × 2.50) / 1,000,000 = (6.3 + 67.5) / 1,000,000 = $0.0000738     about 1/135 of a cent
```

- These are Google's prices for `gemini-3.5-flash-lite` on the paid tier, in US dollars per 1 million tokens, from
  the [Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing), checked on 2026-10-17. Prices change,
  so check that page before you rely on them.
- **On the free tier, these calls cost nothing.** The page shows what they *would* cost on the paid tier.
- **An output token costs about 8 times an input token** ($2.50 against $0.30). A long answer costs much more than a
  long question, which is why `max_output_tokens` is the first thing to cap.
- 10,000 welcomes like this one would cost about $0.74. Bigger prompts, like whole documents, are where token counts
  start to matter.

Python writes a float this small in its own way: `estimate_cost(21, 27)` prints as `7.379999999999999e-05`. That's
0.0000738 (`e-05` means "times 10 to the power -5"), plus a tiny rounding error, because most decimals can't be
stored exactly in a float. So `python hello.py` prints the cost with `dollars()`, the way the page does:

```python
def dollars(usd: float) -> str:
    return f"${usd:.7f}"
```

The JSON from `/api/hello` keeps the plain number: `"cost_usd":3.13e-05` for the cut-off welcome.

### The server and the page

```python
class HelloIn(BaseModel):
    """The JSON body: a name, and how many output tokens this call may use (10 to 200)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=40)
    # ge / le: greater than or equal to, less than or equal to. Anything outside 10 to 200 is a 422.
    max_output_tokens: int = Field(default=MAX_OUTPUT_TOKENS, ge=10, le=MAX_OUTPUT_TOKENS)
```

- A max outside 10 to 200 gets a 422 (`greater_than_equal` or `less_than_equal`), and so does a fraction like 50.5
  (`int_from_float`). Nothing reaches Google, so a bad request costs nothing. Leave `max_output_tokens` out of the
  body and you get 200.
- The endpoint is a plain `def hello(...)`, not `async def`: `ask()` waits for Google with ordinary blocking calls,
  so FastAPI runs it in a worker thread, and the server stays free for other requests meanwhile.
- A failed call is a 502. The full reason goes to the server's terminal; the page gets only the error's type.
- The page adds each call as a new row at the top (`calls.prepend(row)`), and shows costs with 7 decimal places
  (`usd.toFixed(7)`), because one call costs a tiny fraction of a cent.

Each click makes two requests to Google: the free token count, and the call itself.

### Why there's no temperature setting

**Temperature** is the setting that controls how random a model's choice of words is. Low means predictable, and
high means more varied. You might expect a temperature slider here, comparing 0 with 1.

Google has since **deprecated** temperature, along with `top_p` and `top_k`. For Gemini 3.5 Flash-Lite, Gemini 3.6
Flash and later models, the API says these parameters are "deprecated and ignored", and future models will reject
them with an error ([what's new in Gemini 3.6 Flash and 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6)).
If you set one anyway, `langchain-google-genai` drops it from the request and warns:

```text
UserWarning: Model 'gemini-3.5-flash-lite' uses fixed sampling defaults; the sampling parameter(s) temperature will be ignored.
```

A slider would change nothing, so this project doesn't have one. What you can still see:

- **The answers vary.** Click **Ask Gemini** three times with the same name: three different welcomes. The model
  picks its words with some randomness, and on these models you can't turn that off.
- **To make answers more consistent**, Google's advice is a system instruction with explicit rules
  ([project 13](../13-gemini-system-prompt/README.md) adds a system prompt). Examples of the answer you want are
  another way to shape answers ([project 14](../14-gemini-few-shot/README.md)).
- **`max_output_tokens` is the setting that matters for cost**, so that's the box on this page.

## Run it

```bash
cd tutorials/11-gemini-tokens
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the `.env` from [Before you start](#before-you-start) in place:

```bash
python config.py                     # GOOGLE_API_KEY is set.
python hello.py                      # one call for Raghu, and its numbers
python hello.py Asha 10              # at most 10 output tokens: cut off, finish_reason MAX_TOKENS
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

`python hello.py Asha 10` prints something like this:

```text
Direct use of automatic function calling (AFC) in Models.generate_content is not recommended. ...
Welcome, Asha! LangChain

   finish_reason: MAX_TOKENS
  counted_tokens: 21
    input_tokens: 21
   output_tokens: 10
 thinking_tokens: 0
      latency_ms: 610
        cost_usd: $0.0000313
```

(made-up example: Gemini's words and numbers change every time)

The first line is a warning from `google-genai`, the library under `langchain-google-genai`, the same one as in
[project 10](../10-gemini-llm/README.md#when-things-go-wrong). It changes nothing here. `python hello.py` prints it
on every run; the server prints it once, on its first call.

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 (or `/index.html`) | `https://<codespace-name>-8000.app.github.dev` (or `/index.html`) |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

The curl examples are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"name": "Asha", "max_output_tokens": 10}'
# {"answer":"Welcome, Asha! LangChain","finish_reason":"MAX_TOKENS","counted_tokens":21,"input_tokens":21,
#  "output_tokens":10,"thinking_tokens":0,"latency_ms":610,"cost_usd":3.13e-05}
#  (made-up example; 3.13e-05 is how JSON writes 0.0000313)

curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" \
     -d '{"name": "Asha", "max_output_tokens": 5}'
# 422: {"detail":[{"type":"greater_than_equal","loc":["body","max_output_tokens"],
#                  "msg":"Input should be greater than or equal to 10",...}]}   no call, no cost
```

Every run of `hello.py`, every click and every `curl` that gets past the checks is a real call to Gemini, and uses
your key's quota.

## Test it

`tests/test_hello.py` has **21 tests: 19 plain and 2 live**. The plain tests make no call and need no key or network.

- **Cost** (4): the prices are per million tokens, a typical call costs $0.0000738, output costs more than input, and
  `dollars()` shows 7 decimal places.
- **The report** (3): the numbers read out of a hand-built reply shaped like Gemini's (its text a list of content
  blocks), thinking tokens counted in the output and its cost, and `MAX_TOKENS` for a cut-off answer.
- **The model, the chain and `ask()`** (4): the model's settings; `chain_for(10)` puts the cap on the model, not the
  chain, and leaves `model` alone; `ask()` with a stand-in model (no Gemini) counts the prompt first, then makes the
  call with this call's cap; and with no key, `python hello.py` stops with the message, not a stack trace.
- **The endpoint** (6), with `ask()` swapped out (`monkeypatch.setattr(main, "ask", ...)`): the name and the cap are
  passed on, the cap defaults to 200, three bad bodies get a 422 and no call, and a failed call gets a 502 without
  the details.
- **The page** (2): `/` and `/index.html` serve it, with no key in it.
- **Live** (2): one call reports tokens, time and cost of the right shape, and a cap of 10 ends with `MAX_TOKENS`
  and at most 10 output tokens. Each one is a real call plus a free count.

Costs are compared with `pytest.approx`, a tiny tolerance, instead of `==`: float sums aren't exact, and
`estimate_cost(21, 27)` is `7.379999999999999e-05`, not `0.0000738`.

```bash
python -m pytest                     # all 21: the 2 live ones are skipped when there is no key
python -m pytest -m "not live"       # only the 19 plain ones: no call, no cost
python -m pytest -m live             # only the 2 live ones: two real calls
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No key | `python hello.py` stops at once: `Can't build the chain: GOOGLE_API_KEY is not set. ...`. `uvicorn main:app --reload` prints `Uvicorn running on ...` and then the same line, but serves nothing: the page won't load | Copy `.env` as in [Before you start](#before-you-start), then stop the server (Ctrl+C) and start it again |
| An empty or too long name, or a max that isn't a whole number from 10 to 200 | A 422 and no new row, for example `max_output_tokens: Input should be greater than or equal to 10` (an empty max box counts as 0). Nothing is sent to Google | Fix the box |
| A wrong key, no quota left, no network | A 502, with the error's name in brackets. With a wrong key the page says `Gemini didn't answer (ClientError). The server's terminal says why.`, and the terminal shows `400 INVALID_ARGUMENT ... API key not valid`: the free count is the first request to reach Google, so it fails first, with the `google-genai` library's own error name (project 10's call showed `GoogleInvalidRequestError`) | Read the server's terminal. For a key problem, check `.env` ([project 9](../09-gemini-key/README.md)) |
| The answer stops mid-sentence | Finish says `MAX_TOKENS` | Nothing is broken: that's the cap. Raise the max to let it finish |

## Things to try

1. **Watch the cap cut an answer off.** Run `python hello.py Asha 10`, then `python hello.py Asha 200`. The first
   ends with `finish_reason: MAX_TOKENS` and at most 10 output tokens; the second ends with `STOP`, with more output
   tokens and a higher `cost_usd`. That's two real calls.
2. **Count some tokens yourself.** This prints how many tokens a short word and a long word take. It makes two free
   count requests and no model call:

   ```bash
   python -c "from hello import model; print(model.get_num_tokens('cat'), model.get_num_tokens('internationalization'))"
   ```

3. **Ask for a temperature anyway.** Add `temperature=0` to `ChatGoogleGenerativeAI(...)` in `hello.py` and run
   `python hello.py`. You get the `UserWarning` shown above, and the request goes out without it. Take it out again.
4. **Change a price.** Set `PRICE_PER_MILLION_OUTPUT = 5.00` in `hello.py`. `python hello.py Asha 10` now shows a
   higher `cost_usd` (for 21 tokens in and 10 out, $0.0000563 instead of $0.0000313), and
   `python -m pytest -m "not live"` fails 4 tests, because they pin the prices this README quotes. Put it back.

## Next

**[Project 12 · Streaming answers](../12-gemini-stream/README.md)**: the words appear as Gemini writes them, instead
of all at once at the end.
