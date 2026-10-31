# 09 · API (Advanced)

Put the engine behind an HTTP API that's safe in front of real users. Only callers with a key get in, and no caller
can flood it. Every request can be followed through the logs, and the logs never hold a question or a key. Every
failure comes back in one shape. Answers can stream as they're written, and users can rate them. Advanced 08's engine
is unchanged underneath; this project adds the API around it, and the streaming path inside it. Built with
**FastAPI**, **uvicorn**, **LangChain**, **Qdrant** and **SQLite** (the feedback).

> **Needs:** Python 3.11 or newer and a Gemini API key; or no key, with the stand-in models.
> **Production version of:** [Basic · 09 · API](../../Basic/09-api/README.md),
> built on [Advanced · 08](../08-rag-engine/README.md).

---

## 🎯 What This Project Does

- **Only allowed callers**: every `/v1` route needs `Authorization: Bearer <key>`. Keys are made by
  `python main.py add-key NAME` and shown once; only their SHA-256 hashes are kept, in `data/api_keys.toml`
- **A rate limit per caller**: 30 requests a minute by default (a token bucket); over it, `429` with `Retry-After`
- **Request limits**: a body over 16 KB is refused before it's read (`413`), a question over 500 characters is
  refused (`422`), and the engine's deadline cuts off a slow answer (`504`)
- **A request ID for every request**: a valid `X-Request-ID` sent in is kept, else one is made. It comes back in the
  header and in every error, and it's on every log line written while the request is served
- **JSON logs, one line per request**: route, status, time, caller, an error's code, and for an answer its status,
  tokens, cost and each stage's time. Never the question, the answer or a key
- **One error shape**: `{"error": {"code", "message", "request_id", "retryable", "details"?}}`, for a bad request, a
  missing key, a limit, a part that's down, a deadline and the server's own bugs (which never show their text)
- **Health checks**: `/health/live` (the process runs) and `/health/ready` (the store holds the knowledge base, and
  neither breaker is open)
- **Streaming**: `POST /v1/query/stream` sends server-sent events, the answer as the model writes it, then the checked
  answer with its sources. A sensitive value is never shown, even in part, while it streams
- **Feedback**: `POST /v1/feedback` rates an answer up or down by its request ID; `python main.py feedback` lists the
  ones rated down, to add to the evaluation set
- **Versioned routes and CORS**: everything under `/v1`; a browser may call it only from the pages `cors_origins`
  names
- **A load test**: `load_test.py` shows the rate limit holding while the server stays responsive

**Try it:** `python pipeline.py`, then `python main.py add-key me`, then `python main.py`, and open
http://127.0.0.1:8000/docs.

---

## 🏗️ Architecture

```text
client ──→ RequestMiddleware: a request ID; the body's size; the access line; security headers; a 500 for a bug
             └─→ CORS ──→ route ──→ caller(): the key's hash ──→ its rate limit ──→ the body checked
                                       │
       ┌──────────────────┬────────────┴──────┬───────────────────┬─────────────────────────────┐
       ↓                  ↓                   ↓                   ↓                             ↓
  POST /v1/query   POST /v1/query/stream  POST /v1/feedback   GET /v1/stats    GET /health/live · /health/ready
       │                  │                   │                                (no key)
       ↓                  ↓                   ↓
  engine.aask()    engine.astream():     FeedbackStore.rate()
       │           "delta" events,        (the same caller's
       │           then "answer"           answers only)
       └──────┬───────────┘
              ↓
  FeedbackStore.record(): the answer kept, redacted, so it can be rated
  an error from a part ──→ one error shape: 502, 503 (+ Retry-After), 504
```

---

## 📋 Prerequisites

- **Python 3.11 or newer**, and a Gemini API key, as in Advanced 04 (or the stand-ins)
- **curl**, to call the API from a terminal (optional: the `/docs` page does the same in a browser)

---

## 🚀 Quick Start

Steps 1 to 4 are Advanced 04's: go to `projects/RAG/IT Knowledge Base/Advanced/09-api`, make and activate a venv,
`pip install -r requirements-dev.txt`, and copy `.env.example` to `.env` with your key in it.

### Step 5: Load the Knowledge Base, and Make a Key

```bash
python pipeline.py                  # into data/qdrant, as in Advanced 08
python main.py add-key chat-page    # one key per caller: a page, a script, a teammate
```

```text
A new API key for chat-page. It's shown only now: keep it somewhere safe (only its hash is kept, in ...\data\api_keys.toml).
Send it as: Authorization: Bearer <key>

kb_...
```

Keep the key (it starts with `kb_`); the file holds only its hash. `add-key` with the same name again makes a new key
and the old one stops working.

### Step 6: Serve It

```bash
python main.py                      # http://127.0.0.1:8000, its routes at /docs
```

The server writes a JSON line per request to stderr. Qdrant on disk (`data/qdrant`) is used by one process at a time:
stop the server before running `pipeline.py` again, or use a Qdrant server (`[vectorstore] location` = its URL).

### Step 7: Ask

In a second terminal (bash: macOS, Linux, Codespaces, Git Bash), with your key in `KEY`:

```bash
curl -X POST http://127.0.0.1:8000/v1/query -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"question": "My VPN keeps timing out", "session_id": "s1"}'
curl -X POST http://127.0.0.1:8000/v1/query -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"question": "and on Mac?", "session_id": "s1"}'
```

With the stand-in models (the chat stand-in quotes the first chunk it's given), from a real run:

```text
{"request_id":"c8c808066a6b4b3685e69cbba088660f","status":"answered","answer":"1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open.","asked":"My VPN keeps timing out","sources":[{"chunk_id":"kb-4c38012d03ec9cc2:resolution:9e9b2077","doc_id":"kb-4c38012d03ec9cc2","title":"VPN Connection Timeout","section":"resolution","system":"VPN"}],"cached":null,"prompt_version":"answer-v1","input_tokens":0,"output_tokens":0,"cost_usd":0.0,"seconds":0.027}
{"request_id":"21e504f6ddcd4814aea5c7fa111e04dc","status":"answered","answer":"Users experience timeout errors when attempting to connect to the corporate VPN from remote locations","asked":"My VPN keeps timing out, and on Mac?","sources":[{"chunk_id":"kb-4c38012d03ec9cc2:problem:92c1daea","doc_id":"kb-4c38012d03ec9cc2","title":"VPN Connection Timeout","section":"problem","system":"VPN"}],"cached":null,"prompt_version":"answer-v1","input_tokens":0,"output_tokens":0,"cost_usd":0.0,"seconds":0.013}
```

The second question was read with the first: `asked` is the follow-up rewritten. A session belongs to its caller, so
another key with the same `session_id` starts afresh. With Gemini, `input_tokens`, `output_tokens` and (with prices
set in `[engine]`) `cost_usd` hold the model's own counts.

### Step 8: Stream an Answer

```bash
curl -N -X POST http://127.0.0.1:8000/v1/query/stream -H "Authorization: Bearer $KEY" \
     -H "Content-Type: application/json" -d '{"question": "How do I reset my password?"}'
```

```text
event: delta
data: {"text": "6. Verify "}

event: delta
data: {"text": "security "}

event: delta
data: {"text": "questions are "}

event: delta
data: {"text": "set up "}

event: delta
data: {"text": "correctly. 7. "}

event: delta
data: {"text": "Use Forgot Security Questions if needed."}

event: answer
data: {"request_id": "e913378987a64e02921ed93797f4f029", "status": "answered", "answer": "6. Verify security questions are set up correctly. 7. Use Forgot Security Questions if needed.", "asked": "How do I reset my password?", "sources": [{"chunk_id": "kb-923c374222d6d588:resolution:043eb76f", "doc_id": "kb-923c374222d6d588", "title": "Password Reset Failed", "section": "resolution", "system": "Active Directory"}], "cached": null, "prompt_version": "answer-v1", "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "seconds": 0.051}
```

Each `delta` adds to the answer shown; the last event, `answer`, is the checked answer to keep. The deltas joined are
the same text, unless the checks changed it: an answer that cites nothing ends as the "not covered" reply, so a page
shows `answer`'s text in place of what streamed. A failure mid-stream is an `error` event in the one error shape; a
failure before the first piece gets its own status code, as `/v1/query` does. The last 40 characters of what's
written are held back until more arrives, so a value that spans words (a card number with spaces) is redacted whole
before any of it shows. The stand-in streams its answer a word at a time; Gemini streams its JSON as it writes it.

### Step 9: Rate an Answer, and Read the Ratings

```bash
curl -X POST http://127.0.0.1:8000/v1/feedback -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"request_id": "7c1c69d539e24efba62be1dbeec33845", "rating": "down", "comment": "It didn'\''t say which Outlook version"}'
python main.py feedback --csv data/rated_down.csv
```

```text
{"request_id":"7c1c69d539e24efba62be1dbeec33845","rating":"down"}
```

```text
Feedback: 35 answers kept (for 30 days), 0 rated up, 1 rated down
  54a632368d594976b797b8326372feaf (answered, cited 1) My Outlook attachments won't open: It didn't say which Outlook version
Review them: a question the knowledge base should answer belongs in data/eval_questions.csv, with the article that answers it
```

Each answered request is kept for 30 days (`keep_answered_days`), its question redacted first, so it can be rated by
the caller it was given to. The two outputs above come from two runs, so their request IDs differ.

### Step 10: When It Says No

From the same run: no key, a question over 500 characters, a request ID that isn't one of yours, and (from a run with
a limit of 1 a minute) one request too many:

```text
401  {"error":{"code":"UNAUTHORIZED","message":"An API key is needed: send it as Authorization: Bearer <key>","request_id":"ed21bdcaf3bf42928a10be6ce586100c","retryable":false}}
422  {"error":{"code":"INVALID_REQUEST","message":"The request isn't valid: question: String should have at most 500 characters","request_id":"0cf39fdb18a24fb496b7dd2f20d457b1","retryable":false,"details":[{"field":"question","message":"String should have at most 500 characters"}]}}
404  {"error":{"code":"NOT_FOUND","message":"No answer with the request ID nope was given to this API key in the last 30 days","request_id":"e4d8369e734c4840a03527479ecdda9b","retryable":false}}
429  {"error":{"code":"RATE_LIMITED","message":"Over 1 request a minute: try again in 60 s","request_id":"356605f189974117a89c45f169dbcd72","retryable":true}}   Retry-After: 60
```

And the server's lines for the last run, one per request (a 401 has no caller yet; nothing of the question):

```text
{"time": "2026-10-31T02:33:55.968Z", "level": "INFO", "logger": "api", "request_id": "5fa1bcdf52d54c3ea6efb01d383f086a", "message": "POST /v1/query 401", "method": "POST", "path": "/v1/query", "status": 401, "ms": 0.9, "error_code": "UNAUTHORIZED"}
{"time": "2026-10-31T02:33:56.019Z", "level": "INFO", "logger": "api", "request_id": "6f116a164ee24b63aecf1d4e5bc010d2", "message": "POST /v1/query 200", "method": "POST", "path": "/v1/query", "status": 200, "ms": 44.0, "caller": "chat-page", "answer_status": "answered", "cached": "no", "calls": 1, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "trace_id": "37c276128abf4814", "stages_ms": {"condense": 0.0, "cache": 14.5, "retrieve": 4.4, "answer": 5.8}}
{"time": "2026-10-31T02:33:56.040Z", "level": "INFO", "logger": "api", "request_id": "356605f189974117a89c45f169dbcd72", "message": "POST /v1/query 429", "method": "POST", "path": "/v1/query", "status": 429, "ms": 0.6, "caller": "chat-page", "error_code": "RATE_LIMITED"}
```

### Step 11: Load It

```bash
python load_test.py --key $KEY --clients 20 --seconds 20
```

```text
Load test: 20 clients for 20.0 s, one key, a limit of 30 a minute
  Requests: 6560; 31 x 200, 6529 x 429
  Answered (200): median 61 ms, 95th percentile 293 ms
  /health/live while busy: 39 checks, median 16 ms, slowest 25 ms
  Rate limit: 31 answered, at most 40 allowed in 20.0 s: held
```

Twenty threads sent 6,560 requests in 20 seconds with one key. The limit let through what one caller may have: the
burst of 30, plus one every 2 seconds, less what the steps before had used. Meanwhile the health check, which anyone
may call, stayed fast. The server wrote one log line per request, and neither the key nor a question was in any.

---

## 📁 Project Structure

```text
09-api/
├── main.py                       # serve (the default), add-key NAME, feedback [--csv PATH]
├── api.py                        # create_app(): the routes, the request middleware, the error shape, readiness
├── security.py                   # ApiKeys (hashes only), add_key(), RateLimiter (a token bucket per caller)
├── feedback.py                   # FeedbackStore: answered requests, redacted, and their ratings, in SQLite
├── observability.py              # the request ID on every log line; JSON or text lines; secrets masked
├── load_test.py                  # many threads against a running server: the rate limit, and the health check's time
├── answering.py                  # + stream(): the answer as it's written, redacted as it goes
├── rag_engine.py                 # + stream() and astream(); a breaker that guards a streamed call whole
├── wiring.py                     # + make_api(); Gemini bound to the answer's JSON schema, to stream it
├── settings.py                   # + ApiSettings
├── pipeline.py, retriever.py, evaluation.py, vector_store.py, embedding.py, config.py, chunking.py, manifest.py,
│   knowledge_base_loader.py, article.py, sensitive_data.py, utils.py, prompts/
├── kb_settings.toml              # ..., [engine], and now [api]
├── data/                         # Advanced/08's data files; api_keys.toml and feedback.sqlite3 written here (not in git)
└── tests/
    ├── test_api.py               # every route, every refusal, streaming, the logs, the limit under load
    ├── test_main.py              # add-key, feedback, and the real server answering over HTTP
    ├── test_security.py, test_feedback.py, test_observability.py
    └── the tests of Advanced/08, with streaming added to test_answering.py and test_rag_engine.py
```

---

## 🔧 Configuration

### `[api]` in `kb_settings.toml`

| Setting | Default | What it is |
|---|---|---|
| `host` | `"127.0.0.1"` | `0.0.0.0` takes requests from other machines too |
| `port` | 8000 | |
| `keys_file` | `"data/api_keys.toml"` | each caller's name and its key's SHA-256: `python main.py add-key NAME` |
| `requests_per_minute` | 30 | each caller's limit, in bursts of up to as many |
| `max_body_bytes` | 16384 | a bigger request is refused before it's read |
| `cors_origins` | `["http://localhost:8000", "http://127.0.0.1:8000"]` | the pages that may call it from a browser |
| `feedback_path` | `"data/feedback.sqlite3"` | answered requests and their ratings |
| `keep_answered_days` | 30 | how long an answer can be rated (its redacted question is kept that long) |
| `log_format` | `"json"` | `"text"` for reading in a terminal |
| `log_level` | `"INFO"` | `DEBUG` adds a line per health check |

On a server, set them from the environment, as Advanced 08 allows for every setting: `KB__API__HOST=0.0.0.0`,
`KB__API__KEYS_FILE=/run/secrets/api_keys.toml`, `KB__API__CORS_ORIGINS='["https://help.example.com"]'`.

### The Routes

| Route | Key | What it does |
|---|---|---|
| `POST /v1/query` | yes | `{"question", "session_id"?}` → the checked answer, its sources, tokens, cost |
| `POST /v1/query/stream` | yes | the same, as server-sent events: `delta`s, then `answer` (or `error`) |
| `POST /v1/feedback` | yes | `{"request_id", "rating": "up" or "down", "comment"?}` |
| `GET /v1/stats` | yes | what the engine runs with, the feedback's counts, the limits |
| `GET /health/live` | no | 200 while the process runs |
| `GET /health/ready` | no | 200, or 503 when the store is empty or unreachable, or a breaker is open |

### The Error Codes

| Status | Code | When | Retry? |
|---|---|---|---|
| 401 | `UNAUTHORIZED` | no key, another scheme, or a key no caller has | no |
| 404 | `NOT_FOUND` | no such route, or no such answer for this key | no |
| 405 | `METHOD_NOT_ALLOWED` | e.g. `GET /v1/query` | no |
| 413 | `REQUEST_TOO_LARGE` | the body is over `max_body_bytes` | no |
| 422 | `INVALID_REQUEST` | a field missing, too long, unknown or malformed: `details` names each | no |
| 429 | `RATE_LIMITED` | over the caller's limit | after `Retry-After` |
| 500 | `INTERNAL_ERROR` | a bug: logged with its traceback, its text never sent | yes |
| 502 | `UPSTREAM_ERROR` | the store, the embedding model or the chat model failed | yes |
| 503 | `UNAVAILABLE` | a breaker is open: the part failed 3 times in a row | after `Retry-After` |
| 503 | `UPSTREAM_DAILY_QUOTA` | the model's quota for the day is used up | after midnight Pacific |
| 503 | `NOT_READY` | the store doesn't hold the knowledge base yet | after `pipeline.py` |
| 504 | `DEADLINE_EXCEEDED` | the question took longer than `[engine] question_timeout_seconds` | yes |

---

## 🧪 Testing

```bash
python -m pytest        # 383 passed  (add -v for one line per test)
```

- **The API**, with FastAPI's test client and the stand-ins: an answer with its sources and request ID; a missing key,
  a bad one, another scheme; a request ID kept or replaced; too many requests; each invalid field; a body too big,
  by its size or as it arrives; a store that's down (502, then 503 with the breaker open); a slow model (504); the
  day's quota; a bug (500, without its text); a streamed answer whose pieces make the checked answer; a failure
  before and while it streams; feedback only by its own caller; a follow-up in a caller's own session; health and
  readiness, with and without the knowledge base; CORS; unknown routes; one access line per request, with nothing
  of the question, the comment or the key; and 60 requests from 10 threads with a limit of 20: exactly 20 answered,
  40 refused, the health check fast
- **The server itself**: `pipeline.py`, `add-key` and `main.py` run as a user runs them; a question over HTTP, and its
  JSON access line
- **Keys, limits, feedback, logs**: hashes only; a bad keys file named; the token bucket's burst and refill; ratings
  kept, redacted, expired; request IDs and fields; JSON and text lines; secrets masked
- **Streaming in the answerer and the engine**: the pieces make the checked answer; a card number never shown in
  part; an answer turned down ends "not covered"; no streamer, one piece; a cached answer, one piece; a broken stream
  counts against the breaker; `astream()` keeps the deadline

No key and no network, except the one end-to-end test's own local server.

---

## 🎓 Key Concepts Demonstrated

### 1. Keys Are Kept as Hashes

A keys file that leaks gives no one access: it holds SHA-256 hashes of 256-bit random keys. The key itself is shown
once, never stored, never logged.

### 2. A Budget per Caller

The rate limit is a token bucket per key: a burst, then a steady rate. One caller's flood is refused before it costs
anything (0.6 ms for the 429 above), while everyone else, and the health check, is served.

### 3. Follow a Request Through the Logs

A user quotes a request ID; one search finds its line: who asked, how long each stage took, what it cost. The ID
reaches every line written while the request is served, in the worker threads too, through a context variable.

### 4. Logs That Can't Leak

The access line holds IDs, codes, counts and times, never text a user typed. A test asks a question with a marker
word in it and checks that no log line holds the word, the comment or the key.

### 5. One Error Shape

A client handles every failure one way: `code` to branch on, `retryable` and `Retry-After` to know when to try again,
`request_id` to quote. A part's own error text, and a bug's, stay in the log.

### 6. Stream, but Check

The answer streams as it's written, so a user sees it start at once, but nothing unchecked has the last word: the
final event carries the checked answer, and while it streams, the tail is held back so redaction sees each value
whole.

### 7. Live Is Not Ready

A load balancer restarts a process that isn't live, and sends no traffic to one that isn't ready: here, one whose
store is empty or whose breaker is open. Neither check calls the model, so probes cost no quota.

---

## 🛠️ Troubleshooting

**Issue**: `ERROR No API key yet, so no one could call the API`
**Fix**: Add one: `python main.py add-key NAME`. The server won't start without a caller who could use it.

**Issue**: Every request gets `503 NOT_READY`
**Fix**: The store holds no knowledge base yet: stop the server, run `python pipeline.py`, start it again.
`/health/ready` says what's wrong.

**Issue**: `Qdrant's folder ... is open in another process`
**Fix**: The server holds `data/qdrant`. Stop it before running `pipeline.py`, or use a Qdrant server.

**Issue**: A browser page gets a CORS error
**Fix**: Add the page's origin (scheme, host and port) to `cors_origins`.

**Issue**: The server stops answering when another program starts it
**Fix**: The server writes a log line per request to stderr. A program that pipes stderr but only reads it at the
end fills the pipe (about 4 KB on Windows), and the next log line blocks the server. Send stderr to a file, or read
it as it comes.

**Issue**: Answers don't change after the knowledge base did
**Fix**: The answer cache's scope holds the knowledge base's version, read when the server starts: restart the server
after `pipeline.py`.

---

## 📚 Next Steps

**[10 · Chat Page (Advanced)](../10-chat-page/README.md)**: a page on this API: streaming replies, clickable sources,
safe rendering and accessibility.

### Ideas to Try

- Give two callers their own keys, and push one past its limit: the other's requests still go through.
- Set `log_format = "text"` and read the access lines in a terminal.
- Send `X-Request-ID: my-test-1` with a question, then find its line in the log.
