# 10 · Chat Page (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 10 · Chat Page](../../Basic/10-chat-page/README.md)

The basic version is a page served by the same server: type a question, see the answer and its sources. This version
makes the page something people can rely on every day: answers appear as they're written, sources can be opened,
nothing the model writes can run as code in the page, and it works with a keyboard, a screen reader and a phone.

---

## 🎯 What This Project Will Do

- **Show answers as they stream in**, with a way to stop one
- **Make sources useful**: each one opens its article's snippet, and the answer marks which source each part came from
- **Render model output safely**: text, never HTML, with a strict content security policy
- **Handle every state**: loading, empty, slow, failed, not covered, and retry
- **Work for everyone**: keyboard, screen readers, and narrow screens
- **Collect feedback**: thumbs up or down on each answer, sent with its request ID

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Streaming display** | The answer drawn as server-sent events arrive, with a stop button | The page feels quick even when the full answer takes several seconds |
| 2 | **Safe rendering** | Model output inserted as text, or as Markdown through a sanitizer, never as raw HTML | An answer containing `<script>` can't run in the user's browser |
| 3 | **Content security policy** | CSP and other security headers from the server | Even a missed bug can't load outside scripts |
| 4 | **Clickable sources** | Each source shows its title, system and snippet, and opens the full chunk | Users can check the answer against the article themselves |
| 5 | **All the states** | Clear messages for loading, no results, "not covered", a timeout, a rate limit and a server error, with retry | Users always know what's happening and what to do |
| 6 | **Conversation view** | Earlier questions and answers kept on the page and sent as the session | Follow-up questions work the way people expect |
| 7 | **Accessibility** | Labels, focus order, live regions for new answers, contrast, and keyboard use, checked with an audit tool | Everyone can use it, including with a screen reader |
| 8 | **Feedback buttons** | Thumbs up or down per answer, posted with its request ID | Bad answers are reported where they happen |

---

## 🏗️ Planned Architecture

```text
input ──→ POST /v1/query/stream ──→ event stream ──→ answer area (text only, sanitized)
                                          │
                                          └──→ sources (title · system · snippet · open)
                                                       │
                                     👍 / 👎 ──→ POST /v1/feedback (request ID)

states: idle · loading · streaming · done · not covered · error (retry) · rate-limited (wait)
```

---

## ✅ Done When

- A test answer containing HTML and a script tag shows as plain text, and the script never runs
- Browser tests for each state, and for streaming, stopping and retrying
- An accessibility audit with no serious issues, and the page usable with the keyboard alone

---

## 📚 Next Steps

**[11 · Qdrant in Docker (Advanced)](../11-qdrant-in-docker/README.md)**: the app in containers, secured, backed up
and built by CI.
