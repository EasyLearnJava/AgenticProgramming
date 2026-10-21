# 09 · API (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 09 · API](../../Basic/09-api/README.md)

The basic version serves the engine with FastAPI: `POST /api/query`, `GET /api/stats` and `GET /api/health`, with the
request checked before it costs anything. This version makes the API safe to put in front of real users: only
allowed callers get in, nobody can flood it, every request can be followed through the logs, and answers can stream.

---

## 🎯 What This Project Will Do

- **Let only allowed callers in**: API keys or tokens, checked on every request
- **Limit each caller's rate** and the size of each request
- **Follow every request**: a request ID in every log line and every response
- **Fail the same way every time**: one error format, with a code, a message and the request ID
- **Know when it's ready**: separate checks for "alive" and "ready to answer"
- **Stream answers** as they're written, and **take feedback** on each answer

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Authentication** | API keys (or JWTs) checked by a FastAPI dependency; keys stored hashed, never logged | Only known callers can spend the model budget |
| 2 | **Rate limiting** | Requests per minute per key, with `429` and `Retry-After` | One caller can't run up costs or slow everyone else down |
| 3 | **Request limits** | Body size, question length and timeouts per request | Huge or slow requests are refused early |
| 4 | **Request IDs** | An ID per request, returned in a header and written in every log line | A user's complaint can be matched to the exact log lines |
| 5 | **Structured logging** | JSON logs with the request ID, route, status, timing and token counts, with no question text or keys | Logs can be searched and charted, and leak nothing |
| 6 | **One error model** | A single JSON error shape for validation, auth, limit, upstream and server errors | Clients handle every failure the same way |
| 7 | **Liveness and readiness** | `/health/live` (the process runs) and `/health/ready` (the store and the model answer) | A deployment sends traffic only to instances that can answer |
| 8 | **Streaming** | `POST /api/query/stream` with server-sent events: the answer as it's written, then the sources | Users see the answer start in a second, not after the whole of it is ready |
| 9 | **Feedback** | `POST /api/feedback` with a thumbs up or down and the request ID, stored for evaluation | Real users' judgements feed the evaluation set |
| 10 | **Versioning and CORS** | Routes under `/v1`, and CORS limited to known origins | The API can change without breaking clients, and only allowed pages can call it |

---

## 🏗️ Planned Architecture

```text
client ──→ CORS ──→ request ID ──→ auth ──→ rate limit ──→ validate ──→ route
                                                                         │
                       ┌─────────────────────┬───────────────────────────┼──────────────────────┐
                       ↓                     ↓                           ↓                      ↓
                 /v1/query            /v1/query/stream             /v1/feedback       /health/live · /ready
                       │                     │
                       └──→ engine ──→ answer + sources ──→ JSON log line (request ID, timing, tokens)
```

---

## ✅ Done When

- Tests for a missing key, a bad key, too many requests, a too-long question, a store that's down, and a streamed
  answer, each with the expected status code and error shape
- A log line per request with its ID and timing, and a test that no question text or key appears in the logs
- A load test showing the rate limit holds and the server stays responsive

---

## 📚 Next Steps

**[10 · Chat Page (Advanced)](../10-chat-page/README.md)**: streaming replies, clickable sources, safe rendering
and accessibility.
