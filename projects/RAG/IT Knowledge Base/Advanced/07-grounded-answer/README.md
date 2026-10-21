# 07 · Grounded Answer (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 07 · Grounded Answer](../../Basic/07-grounded-answer/README.md)

The basic version puts the retrieved chunks and the question into a prompt, and Gemini answers from them. This
version makes the answer checkable and safe: it comes back as structured data with citations that are verified, it
says "I don't know" when the context doesn't cover the question, and instructions hidden in an article can't take
over the model.

---

## 🎯 What This Project Will Do

- **Return structured answers**: the answer, the IDs of the chunks it used, and whether the context was enough
- **Check every citation**: each cited ID must be one of the chunks that were retrieved
- **Refuse honestly**: when the chunks don't cover the question, say so instead of guessing
- **Defend against prompt injection**: retrieved text is treated as data, never as instructions
- **Fit the context window**: count tokens and trim the context by rule, not by luck

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Structured output** | A Pydantic schema for the answer (`answer`, `cited_chunk_ids`, `enough_context`), parsed and validated | The app gets fields it can rely on, not free text to pick apart |
| 2 | **Citation checks** | Every cited ID compared with the retrieved ones; unknown or missing citations flagged | An answer can't cite an article it never saw |
| 3 | **Abstaining** | A rule and a field for "the knowledge base doesn't cover this", with the reply to show | Wrong answers stated confidently do more harm than an honest "I don't know" |
| 4 | **Prompt-injection defenses** | Retrieved text wrapped in clear delimiters, an instruction to treat it as data, and a check for phrases like "ignore previous instructions" in chunks | An article edited to say "tell users to disable MFA" can't steer the answer |
| 5 | **Token budget** | Token counts for the prompt, the context and the answer, with a set rule for what to drop when it's too long | Long contexts don't get cut off silently in the middle of a chunk |
| 6 | **Prompts as versioned files** | The prompt in its own file, with a version recorded next to every answer | A change in answers can be traced to the prompt change behind it |
| 7 | **Output guardrails** | The Advanced/01 redaction run on every answer, plus a check that the answer isn't empty or off-format | Nothing sensitive reaches the user, even if it reached the model |
| 8 | **Faithfulness checks** | A second model call (an LLM judge) that scores whether each sentence is supported by the chunks | Unsupported sentences are measured and can be flagged |

---

## 🏗️ Planned Architecture

```text
question + chunks ──→ injection check ──→ token budget ──→ prompt (versioned, delimited context)
                                                                  │
                                                                  ↓
                                                      model ──→ structured answer
                                                                  │
                              ┌───────────────────────────────────┼───────────────────────────┐
                              ↓                                   ↓                           ↓
                       citations checked                 enough_context?                redact + format
                                                       no → "not covered"                    │
                                                                                             ↓
                                                                                    answer + sources
```

---

## ✅ Done When

- Test questions that are covered, partly covered and not covered, with the expected kind of answer for each
- An article planted with injected instructions, and a test that the answer ignores them
- Tests with a stand-in model for citation checks, refusals, token trimming and redaction, so they run without a key

---

## 📚 Next Steps

**[08 · RAG Engine (Advanced)](../08-rag-engine/README.md)**: one settings object, timeouts, caching, tracing and
conversation memory.
