# 12 · Streaming answers

A script and a page where Gemini's answer appears while it's being written, instead of all at once at the end. The
whole answer takes just as long either way: streaming changes **when you start reading**, and that's what makes an
app feel fast.

```text
POST /api/hello {"name": "Asha"}  ->  plain text, sent piece by piece as Gemini writes it

without streaming:  ........................ (nothing for 2.4 s) ........................  the whole answer
with streaming:     Welcome, Asha! ··· LangChain is a ··· framework for ··· ... ··· Have fun!
                    ^ first words after 0.4 s                                       ^ all of it after 2.4 s
                    (made-up example: Gemini's words, its pieces and the timings change every time)
```

## What you'll build

- **`hello.py`**: `python hello.py Asha` prints Gemini's three-paragraph welcome piece by piece as it arrives, then
  how long the first words and the whole answer took.
- **`main.py`**: a FastAPI server. `POST /api/hello` with `{"name": "Asha"}` answers with plain text, sent piece by
  piece with `StreamingResponse`. A bad name gets a 422; a failure before the first piece gets a 502; a failure
  part-way keeps the text so far and adds `[Gemini stopped before the end of the answer.]`.
- **`index.html`**: a page where the answer grows as it arrives, with the time to the first words and to the whole
  answer.

## What you'll learn

- **`chain.stream()` / `chain.astream()`**: the answer in pieces ("chunks"), as long as each step after the model passes them on.
- **Generators and async generators**: `yield` hands out one value at a time; `async for` and `anext()` read them.
- **`StreamingResponse`**: FastAPI sends each piece to the browser as soon as it's ready.
- **`res.body.getReader()` with `TextDecoder`**: the page reads the reply piece by piece, in a loop.
- **Time to first token**: how long until the first words, the number that makes an app feel fast.
- **Errors in a stream**: a 502 is only possible before the first piece; after it, the text itself says it stopped.

## What's new since project 11

- [Project 11 · Tokens and cost](../11-gemini-tokens/README.md) made one call and waited for the whole answer. Now the
  answer streams: `hello.py` loops over `chain.stream()`, and `main.py` uses `chain.astream()` with `await anext()`.
  The endpoint is `async def` again (project 11's was a plain `def`), because it waits for each piece with `await`.
- `StrOutputParser` is back: project 11 left it out to read the token counts in the `AIMessage`. The prompt asks for
  three short paragraphs with `MAX_OUTPUT_TOKENS = 400`, instead of one or two sentences with 200, so there's
  something to watch arrive.
- `POST /api/hello` takes just `{"name"}` again, and answers with plain text through `StreamingResponse` instead of
  JSON. The token counts, the cost and the max-tokens box are gone.
- The page reads the reply with `res.body.getReader()` instead of `res.json()`, and splits project 11's one time per
  call into the time to the first words and the time to the whole answer.

## Before you start

- Python 3.11 or newer.
- The key from [project 9](../09-gemini-key/README.md). Each project folder reads its own `.env`, so copy yours into
  this one, once. From this folder, `tutorials/12-gemini-stream`:

  ```bash
  cp ../09-gemini-key/.env .env
  ```

  With a Codespaces secret named `GOOGLE_API_KEY` there's nothing to copy: every project sees it.

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt \| model \| StrOutputParser()`, asking for three short paragraphs. `python hello.py Asha` prints the answer piece by piece, then the timings |
| `main.py` | FastAPI: `GET /` and `/index.html` serve the page; `POST /api/hello` streams the answer as plain text with `StreamingResponse`. A bad name gets a 422; a failure before the first piece gets a 502 |
| `index.html` | The page: reads the stream with `getReader()`, adds each piece to the answer, and shows the timings |
| `config.py` | `load_api_key()`: loads `.env`, checks the key, and raises `MissingKeyError` with a clear message when there's none. The same file as project 9 |
| `.env.example` | The template for `.env`, the file that holds your key. `.env` is in `.gitignore`, so it never goes into git |
| `tests/test_hello.py` | The tests: plain ones, where a stand-in streams the pieces instead of Gemini, and a live one that streams a real answer |
| `tests/conftest.py` | Runs before the tests and checks once for a real key: with none, it gives `hello.py` a fake one and skips the live test |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, only looks in `tests/`, and defines the `live` marker |
| `requirements.txt` | The packages, pinned, the same as project 10: `fastapi`, `uvicorn`, `langchain-core`, `langchain-google-genai`, `google-genai` and `python-dotenv` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |
| `README.md` | This guide |

## How it works

### 1. The chain streams (`hello.py`)

The key (①) and the model (③) work as in project 10. The prompt asks for a longer answer, and the chain has the same
shape as before:

```python
MAX_OUTPUT_TOKENS = 400           # project 10 had 200: room for a longer answer, so you can watch it arrive
...
# ② The prompt asks for more than project 10's one or two sentences: with only a few words, streaming is over before
#    you see it.
prompt = PromptTemplate.from_template(
    "Write a friendly welcome for {name}, who is starting to learn LangChain, in three short paragraphs: "
    "what LangChain is, what they will build first, and a word of encouragement."
)
...
# ④ The chain: the same shape as project 10's. Every chain has stream() as well as invoke(), and here the pieces get
#    through one by one because StrOutputParser passes each piece's text on as it comes. (A plain function step after
#    it, a RunnableLambda, would wait for the whole answer and pass it on in one piece.)
chain = prompt | model | StrOutputParser()
```

Only the call is different. The docstring at the top of `hello.py` puts the two side by side:

```text
    chain.invoke({"name": "Asha"})  ->  waits, then gives the whole answer as one string
    chain.stream({"name": "Asha"})  ->  "Welcome, Asha!", " LangChain is a", " framework for", ...
                                        the answer in pieces ("chunks"), each one as soon as it's ready
                                        (made-up pieces: Gemini's words, and where it cuts them, change every time)
```

`python hello.py` runs the stream in a `for` loop:

```python
    # ⑤ Stream it: print each piece the moment it arrives, and time the first piece and the end.
    start = time.perf_counter()
    first_ms = None
    piece_count = 0
    for piece in chain.stream({"name": name}):           # a for loop: each turn waits for the next piece
        if first_ms is None:
            first_ms = round((time.perf_counter() - start) * 1000)   # the time to the first words
        piece_count += 1
        print(piece, end="", flush=True)                 # flush: show it now, don't wait for the end of the line
    total_ms = round((time.perf_counter() - start) * 1000)
    print(f"\n\nfirst words after {first_ms} ms, all of it after {total_ms} ms, in {piece_count} pieces")
```

- **Gemini sends its answer in pieces as it writes**, and `StrOutputParser` passes each piece's text straight on.
  How big each piece is, and how many there are, is up to Gemini: LangChain hands on each piece as it comes.
- **`print(piece, end="", flush=True)`** prints each piece right after the one before, and shows it at once instead
  of waiting for the end of the line.
- **`time.perf_counter()`** is a stopwatch. The time to the first piece is the **time to first token**: how long you
  wait before you can start reading. The total is about what you'd wait without streaming.

### 2. Generators, in two minutes

`main.py` is built on one Python idea that's new here. A **generator** is a function with `yield`:

```python
def count_to_three():            # a generator: a function with yield
    yield 1                      # hands out 1, then pauses right here
    yield 2                      # carries on from here when the next value is asked for
    yield 3

for n in count_to_three():       # each turn of the loop asks for the next value
    print(n)                     # 1, then 2, then 3
```

In Java terms it's an `Iterator` written as one method: each `next()` runs the method up to its next `yield`, and
nothing runs until the first value is asked for.

`async def` with `yield` makes an **async generator**: the same idea, but getting each value can be awaited (here:
waiting for Gemini's next piece) while the server gets on with other requests. You read one with `async for`, and
`await anext(gen, default)` is the async `next()`: the next value, or `default` if there are none left.

`chain.astream()` returns an async generator, so calling it runs nothing until the first piece is asked for. That's
why `hello()` in `main.py` is `async def` again: it awaits the pieces.

### 3. The server waits for the first piece, then streams the rest (`main.py`)

```python
    pieces = chain.astream({"name": body.name})          # nothing runs yet: this only sets up the stream

    # ① Wait for the first piece. ...
    try:
        first = await anext(pieces, "")
    except Exception as err:
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err

    # ② The whole answer, as an async generator (an `async def` with `yield`): the first piece, then the rest. ...
    async def first_then_the_rest():
        yield first
        try:
            async for piece in pieces:
                yield piece
        except Exception as err:                         # it failed part-way: say so at the end of the text
            logger.warning("Gemini stopped part-way: %s", err)
            yield STOPPED

    # ③ StreamingResponse sends each yielded piece as soon as it's ready, instead of waiting for the end. ...
    return StreamingResponse(
        first_then_the_rest(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

A normal endpoint returns its answer once, at the end. `StreamingResponse` takes a generator instead, and sends each
yielded piece to the browser as soon as it's ready.

**Why wait for the first piece?** Every HTTP reply starts with a status (`200`, `502`, ...) and headers, then the
body. FastAPI starts the `StreamingResponse` as soon as `hello()` returns it, and it sends the status and the headers
**first, before it asks the generator for any text**. You can see it in Starlette, the library FastAPI is built on:
`StreamingResponse.stream_response()` sends the start of the reply, status included, and only then loops over the
generator. After that, the status can't change. So `main.py` gets the first piece *before* it returns the
`StreamingResponse`, while a 502 is still possible. Most failures, like a wrong key, no quota or no network, happen
right there, on the first request to Gemini. Without the wait, a wrong key gives `HTTP/1.1 200 OK` straight away and
then a reply that breaks off (Things to try shows you).

**A failure after the first piece** can only be reported inside the text. `first_then_the_rest()` catches it, logs
the reason in the server's terminal, and yields `STOPPED`, so the reader gets the text so far and then
`[Gemini stopped before the end of the answer.]`. The status stays `200`: it went out just before the first piece.

**`anext(pieces, "")`** runs the chain until Gemini sends its first piece. The `""` is what it gives back if there
are no pieces at all, and then the reply is an empty 200. Without the `""`, a stream with no pieces would raise
`StopAsyncIteration`, and the `except Exception` would turn it into a 502.

**The two headers** are for proxies between the page and the server, such as Codespaces' port forwarding.
`X-Accel-Buffering: no` asks a proxy to pass each piece on at once instead of collecting the whole reply first
(nginx reads this one), and `Cache-Control: no-cache` says that no cache may hand this reply out again without asking
the server.

### 4. The page reads it piece by piece (`index.html`)

```js
        // Read the body piece by piece, instead of await res.text(), which would wait for all of it.
        const reader = res.body.getReader();
        const decoder = new TextDecoder();         // the pieces arrive as bytes; this turns them into text
        let firstMs = null;
        let reads = 0;                             // one read() can hold several of the server's pieces
        while (true) {
          const { done, value } = await reader.read();   // waits until more of the answer has arrived
          if (done) break;                               // the server has sent everything
          if (firstMs === null) firstMs = ms();
          reads += 1;
          answer.textContent += decoder.decode(value, { stream: true });
          timing.textContent = `First words after ${firstMs} ms… still writing`;
        }
```

- **The pieces arrive as bytes**, and `TextDecoder` turns them into text. `{ stream: true }` handles a character
  whose bytes are split across two reads, which can happen with characters like `é` or `₹`: the decoder keeps the
  first half until the rest arrives.
- **The page counts the browser's reads, not Gemini's pieces.** Pieces that arrive close together come out of one
  `read()`, so the page can show a smaller number than `python hello.py` does for the same kind of answer.
- **The timings** come from `performance.now()`, the browser's stopwatch, started just before the `fetch`.

| The server answers | The page shows |
|---|---|
| 200, with text | the answer as it arrives, then `First words after ... ms, all of it after ... ms (the browser got it in ... reads). Without streaming, you would have seen nothing for ... ms.` |
| 200, with no text | `Gemini sent back an empty answer. The server's terminal may say why.` |
| 422 | what was wrong, for example `name: String should have at least 1 character` |
| 502 | the error's type, for example `Gemini didn't answer (GoogleInvalidRequestError). The server's terminal says why.` |
| any other status, or nothing at all | `Something went wrong: the server answered HTTP 500`, or `Something went wrong:` and the browser's own words, such as `Failed to fetch` |

## Run it

```bash
cd tutorials/12-gemini-stream
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the `.env` copied in (see [Before you start](#before-you-start)):

```bash
python config.py                     # GOOGLE_API_KEY is set.  (or a message saying what to do)
python hello.py Asha                 # the answer piece by piece, then: first words after ... ms, all of it after ... ms, in ... pieces
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

The `/docs` page can call the endpoint too, but it shows the answer only once all of it has arrived. To watch the
pieces arrive, use curl. The curl examples are for bash (macOS, Linux, Codespaces, Git Bash). `-N` tells curl to
print each piece as it arrives instead of saving them up, and `-i` adds the status line and the headers, which come
before any text:

```bash
curl -N -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha"}'

curl -i -N -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha"}'
# HTTP/1.1 200 OK
# ...
# cache-control: no-cache
# x-accel-buffering: no
# content-type: text/plain; charset=utf-8
# Transfer-Encoding: chunked
#
# Welcome, Asha! ...   the text, piece by piece
```

Every click and every `curl` with a good name is a real call to Gemini, and uses your key's quota.

## Test it

```bash
python -m pytest                     # every test; the live one is skipped when there's no key
python -m pytest -m "not live"       # only the plain tests: no call, no cost
python -m pytest -m live             # only the live test: one real streamed answer
```

There are 14 tests: 13 plain and 1 live.

- **The 13 plain tests** never call Gemini:
  - the chain's parts (3): the order (prompt, then model, then parser), the prompt's three short paragraphs with the
    name in them, and the model's name and its cap of 400
  - no key (1): `python hello.py` stops with the message and no traceback
  - the endpoint (7): the pieces come back in order as `text/plain`, with the spaces trimmed off the name that
    reaches the chain; each piece is handed on separately; the two headers for proxies; a failure before the first
    piece gets a 502 with only the error's type; a failure part-way keeps the text so far and adds the
    `[Gemini stopped ...]` line; a stream with no pieces is an empty 200, not a 502; and an empty name gets a 422
    while the chain never runs
  - the page (2): `/` and `/index.html` are served, read the stream with `res.body.getReader()`, and hold no key
- **The live test** streams one real answer with `chain.stream()` and checks that "Asha" is in it and that it came
  in more than one piece. It can't check the exact words, because they change every time.

For the endpoint tests, the chain is swapped for a small stand-in, `monkeypatch.setattr(main, "chain", StandIn([...]))`,
which streams the pieces it's given (and can fail at one of them), so the tests need no key and no network.

FastAPI's `TestClient` runs the app to the end and only then hands back the reply, all in one. So most endpoint tests
check the status, the headers and the text, but can't see the pieces arrive one by one.
`test_each_piece_is_handed_on_separately` calls `hello()` itself and reads the `StreamingResponse`'s generator the
way `StreamingResponse` does: one item per piece.

Without a key, `python -m pytest` ends with `13 passed, 1 skipped`, and `python -m pytest -m "not live"` with
`13 passed, 1 deselected`.

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No key: the `.env` isn't in this folder | `python hello.py` and `uvicorn main:app` stop at once with `Can't build the chain: GOOGLE_API_KEY is not set. ...`. With `--reload`, the message appears but the command keeps running, and the page won't open | Copy the `.env` in (see [Before you start](#before-you-start)). With `--reload`, press Ctrl+C and start the server again: it restarts by itself only when a `.py` file changes |
| A wrong key, on the page or with `curl` | A 502 at once. The page says `Gemini didn't answer (GoogleInvalidRequestError). The server's terminal says why.`, and the terminal says `WARNING:  Gemini call failed: Error calling model 'gemini-3.5-flash-lite' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. ...` | Fix the key in `.env` (or the Codespaces secret), then restart the server |
| A wrong key, with `python hello.py` | A long traceback: the script doesn't catch errors. Its last line says what went wrong: `langchain_google_genai.chat_models.GoogleInvalidRequestError: ... 'API key not valid. ...` | Fix the key in `.env` and run it again |
| Gemini fails part-way through | The text so far, then `[Gemini stopped before the end of the answer.]`. The terminal says `WARNING:  Gemini stopped part-way: ...` | Ask again |
| Gemini blocks the request | The page says `Gemini sent back an empty answer. The server's terminal may say why.`, and the terminal shows `Gemini produced an empty response. Continuing with empty message` | Try another name |
| The words arrive all at once in Codespaces | The whole answer appears in one go | A proxy on the way held the pieces back. Try the page on your laptop (`127.0.0.1:8000`), or `python hello.py Asha`, which goes through no proxy |
| `python hello.py > welcome.txt` (or a pipe) on Windows | The answer stops part-way with `UnicodeEncodeError: 'charmap' codec can't encode character ...`, at a character, such as an emoji, that Windows' old text encoding can't write | Run `export PYTHONUTF8=1` (Git Bash) or `$env:PYTHONUTF8 = "1"` (PowerShell) first, or print straight to the terminal |

The first call in each run also prints this warning in the terminal (the server's version says `AsyncModels`):

```text
Direct use of automatic function calling (AFC) in Models.generate_content_stream is not recommended. ...
```

It comes from `google-genai`, the library under `langchain-google-genai`, and changes nothing here.

## Things to try

1. **Take the wait out.** In `main.py`, replace everything inside `hello()`, below its docstring, with this one line:

   ```python
       return StreamingResponse(chain.astream({"name": body.name}), media_type="text/plain; charset=utf-8")
   ```

   Start the server with a wrong key, which wins over the one in `.env`: `GOOGLE_API_KEY=wrong-key uvicorn main:app`
   (bash). Then run the `curl -i -N` example from Run it. `HTTP/1.1 200 OK` comes back at once, before Gemini has
   even been asked, and then curl stops with `curl: (18) transfer closed with outstanding read data remaining`. The
   terminal shows `"POST /api/hello HTTP/1.1" 200 OK` and then `ERROR:    Exception in ASGI application`, and the
   page says `Something went wrong: ...`. Put the code back: the same request gets a clean 502,
   `{"detail":"Gemini didn't answer (GoogleInvalidRequestError)."}`, and the plain tests pass again.
2. **See where the pieces are cut.** In `hello.py`, change `end=""` to `end="|"` in the `print` inside the loop, and
   run `python hello.py Asha`. A `|` appears after every piece, so you can see where Gemini cut its answer, and count
   the pieces the last line reports.
3. **Add a step that can't stream.** In `hello.py`, add `from langchain_core.runnables import RunnableLambda` and
   make the chain `prompt | model | StrOutputParser() | RunnableLambda(str.upper)`. Now `python hello.py Asha` shows
   nothing for a while, then the whole answer at once, in capitals, and the last line says `in 1 pieces`: a plain
   function step waits for all of its input, so the pieces stop there. The page does the same. Put the chain back
   afterwards: `test_chain_is_prompt_then_model_then_parser` checks it.

## Next

**[Project 13 · Give the model a role: the system prompt](../13-gemini-system-prompt/README.md)**: one question,
answered twice, for a beginner and for an expert, where only the system prompt changes.
