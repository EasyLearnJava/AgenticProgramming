# 12 · Streaming answers

The words appear as Gemini writes them, instead of all at once at the end. The page shows how long the first words
took and how long the whole answer took.

```text
without streaming:  ........................ (nothing for 2.4 s) ........................  the whole answer
with streaming:     Welcome, Asha! ··· LangChain is a ··· framework for ··· ... ··· Have fun!
                    ^ first words after 0.4 s                                       ^ all of it after 2.4 s
                    (made-up timings: yours depend on the answer and the network)
```

The answer takes just as long to finish either way. Streaming changes **when you start reading**.

## What you learn

- **`chain.stream()` / `chain.astream()`**: every chain can stream, giving the answer in pieces ("chunks")
- **An async generator**: a function with `yield`, giving one piece at a time
- **`StreamingResponse`**: FastAPI sends each piece to the browser as soon as it's ready
- **`res.body.getReader()`**: the page reads the reply piece by piece, in a loop
- **Time to first token**: how long until the first words, the number that makes an app feel fast
- **Errors in a stream**: before the first piece you can still send a 502; after it, you can't

## Before you start: the key

As in project 10, copy your `.env` across (or use a Codespaces secret):

```bash
cd projects/12-gemini-stream
cp ../10-gemini-llm/.env .env
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `hello.py` | The chain: `prompt \| model \| StrOutputParser()`, asking for three short paragraphs. `python hello.py Asha` prints the answer piece by piece, then the timings |
| `config.py` | Loads and checks the key: the same file as projects 9 to 11 |
| `main.py` | FastAPI: `POST /api/hello` streams the answer as plain text with `StreamingResponse`. A bad name gets a 422; a failure before the first piece gets a 502 |
| `index.html` | The page: reads the stream with `getReader()`, adds each piece to the answer, and shows the timings |
| `tests/conftest.py` | Skips the live test when there is no key |
| `tests/test_hello.py` | 11 plain tests (a stand-in streams the pieces, no call) and 1 live test (one real streamed answer) |
| `requirements.txt` | The same as project 10 |

## Three steps, from Gemini to your screen

**1. The chain streams** (`hello.py`). It's the same chain as project 10; only the call is different:

```python
chain = prompt | model | StrOutputParser()

chain.invoke({"name": "Asha"})              # waits, then: "Welcome, Asha! LangChain is ..."   (one string)
for piece in chain.stream({"name": "Asha"}):
    print(piece, end="", flush=True)        # "Welcome, Asha!" ... " LangChain is" ... " a framework" ...
```

Gemini sends the answer in pieces as it writes, and `StrOutputParser` passes each piece's text straight on. A
piece can be a few words or a whole sentence: Gemini decides where to cut, not LangChain.

**2. The server passes each piece on** (`main.py`):

```python
pieces = chain.astream({"name": body.name})   # the async twin of stream()
first = await anext(pieces, "")               # wait for the first piece (see "When things go wrong")

async def the_rest():                         # an async generator: each yield sends one more piece
    yield first
    async for piece in pieces:
        yield piece

return StreamingResponse(the_rest(), media_type="text/plain; charset=utf-8", headers={...})
```

A normal endpoint returns once, at the end. `StreamingResponse` takes a generator instead, and sends each yielded
piece to the browser as soon as it's ready.

**3. The page reads it piece by piece** (`index.html`):

```js
const reader = res.body.getReader();          // instead of await res.text(), which waits for the end
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();   // waits for the next piece
  if (done) break;
  answer.textContent += decoder.decode(value, { stream: true });
}
```

The pieces arrive as bytes; `TextDecoder` turns them into text. `{ stream: true }` handles a letter whose bytes
are split across two pieces, which happens with characters like `é` or `₹`.

## When things go wrong

| When | What you see |
|---|---|
| A bad name | A 422, and Gemini is never called |
| Gemini fails **before** the first piece (bad key, no quota) | A 502: `Gemini didn't answer (...)`, and the reason in the server's terminal |
| Gemini fails **part-way** through | The text so far, then `[Gemini stopped before the end of the answer.]` |

Why the difference? A reply starts with its status, `200` or `502`, and **the status is sent with the first
piece**. After that it can't change. So `main.py` waits for the first piece before it starts the reply: most
failures, like a wrong key, happen right there and can still become a proper 502. A failure later can only be
reported inside the text.

## If the words still arrive all at once

A proxy between the browser and the server can collect the pieces and pass them on together. `main.py` sends two
headers that ask proxies not to: `Cache-Control: no-cache` and `X-Accel-Buffering: no`. If the answer still
appears in one go in Codespaces, try the same page on your laptop (`127.0.0.1:8000`), and check
`python hello.py Asha` in the terminal, which never goes through a proxy.

## Run it

```bash
cd projects/12-gemini-stream
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../10-gemini-llm/.env .env      # the key, once (see above)

python hello.py Asha               # the answer piece by piece, then: first words after ... ms, all of it after ... ms
python -m pytest                   # 12 tests: 11 plain, 1 live
python -m pytest -m "not live"     # only the plain ones: no call, no cost

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |

`-N` tells curl to print each piece as it arrives, instead of waiting for the end:

```bash
curl -N -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha"}'
```

The `/docs` page can call the endpoint too, but it waits for the whole answer before it shows anything.

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Part B's next module shapes the answers themselves: a system prompt that gives the model a role, examples it copies,
and answers as typed data.
