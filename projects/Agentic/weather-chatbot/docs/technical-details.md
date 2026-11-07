# Technical Details

Start in `nimbus/chat.py` for an unexpected reply, `nimbus/parks.py` for an unexpected passage, and
`nimbus/travel/` for trip dates or offers. Each path below names the functions that make the decision and
a way to observe the result.

## Follow a weather request

![The weather request from a browser POST to tool calls, an SSE answer and a recorded timeline](images/data-flow.svg)

1. **Receive the question.** For “Will it rain in Paris tomorrow?”, `templates/chat.html` posts to
   `/api/chat`. The browser supplies locale, time zone and bounded history. `read_chat_request()` validates
   them. A question can contain up to 2,000 characters. History is limited to ten alternating messages
   and 16,000 characters in total. History is treated as untrusted text.
2. **Choose the execution path.** `chat()` checks park planning intent, city trip intake, missing hotel dates
   and requests beyond the forecast horizon before accessing Gemini. A city dates-only follow-up can reuse
   the earlier destination. The Paris weather question falls through to the agent. The supported daily
   forecast horizon is 16 days, and hourly output covers up to three days.
3. **Run the graph.** `nimbus/agent.py: make_agent()` binds the tools for this turn. Gemini can request a
   place lookup and then a forecast at the chosen coordinates. LangGraph's `Send` can dispatch independent
   calls in parallel. At most six tool calls fit in a model round. The fifth model call has tools turned off.
   The first model chunk has a ten-second deadline, within the turn's 30-second unauthenticated or 50-second
   authenticated budget.
4. **Return evidence and text.** `nimbus/answer.py` turns graph events into tool starts, tool outcomes and
   text. The chat streams HTML using server-sent events (SSE). Expand a chip to see the tool, its timing
   and outcome. The final Markdown renderer filters links against the permitted sources. If a weather lane
   fails, the request outcome and Activity timeline can retain the failure even after partial output.
   [Agent chapter](step-5.md) · [Streaming chapter](step-2.md).

## Follow a trip through the same endpoint

| Starting point | Code to inspect | What to check |
| --- | --- | --- |
| Broad city request | `travel/city_intake.py`, `travel/hotel_intake.py`, `forecast_horizon.py` | “Plan a trip to Dallas” asks for dates. A weather-specific follow-up can take the ordinary weather path. |
| Named park and weekend | `travel/planner_intake.py`, `weekend_dates.py`, `return_times.py` | The resolved destination, departure time zone and date range. An explicit deadline to arrive home takes precedence over an evening default. |
| Dated park briefing in chat | `travel/briefing.py`, `briefing_page.py`, `conditions.py` | `check_conditions()` runs forecast, stored guidance, NPS notices and NWS point alerts concurrently. The decision uses location, scope, coverage and overlap. |
| Confirmed park trip | `travel/planner_page.py`, `planner.py` | `make_plan()` collects flights, hotels, weather, preparation and NPS outcomes independently under a shared deadline. |
| An individual flight or hotel search | `travel/tools.py`, `service.py`, `kiwi.py`, `trivago.py` | The validated query, provider outcome and offer cards. Chat and the planner reuse the same search service. |

`nimbus/travel/models.py` accepts hotel dates as either `check_in` / `check_out` or the
`checkin_date` / `checkout_date` names a model may emit. The same date-order and stay-length validation
applies to both. A `TravelTurn` shares identical lookups within a request and caps distinct searches at two
per provider. The adapters return up to five validated offers. The browser gets eligible provider links,
while Gemini receives bounded offer facts with those URLs removed. [Travel tool contracts](step-18.md).

## Reproduce a park retrieval

In the [Retrieval Playground](/knowledge/retrieval), select **The Narrows** and ask **What should I know about
flash floods?** Inspect the retrieved section and its source, then compare the highest-ranked candidate with
another candidate. The mode shown on that run explains whether a semantic score contributed.

1. **Build the collection offline.** `nimbus/park_ingest.py` makes passages from reviewed NPS sections.
   The manifest supplies destination and season scope. Each record includes a document ID, source URL,
   section, fetch date and content hash. `write_index()` validates the records and atomically replaces
   `data/parks/index.sqlite`. The request path opens that index read-only.
2. **Limit the candidates.** `ParkKnowledge.resolve()` checks known names and aliases.
   `ParkKnowledge.search()` filters by park, destination and, when supplied, visit season. A matching word
   from another park cannot bring that passage back into the result.
3. **Calculate the scores.** Keyword scoring expands selected terms, gives section headings extra weight and
   accounts for term rarity and passage length. The keyword component is `keyword_score / (1 + keyword_score)`.
   When the query and index use compatible embeddings, the ranker adds their cosine similarity. A passage
   with no keyword hit needs a similarity of at least 0.65 to qualify. Equal totals break by passage ID.
4. **Build the context.** Up to four passages fit within 10,000 characters of passage text. The Playground
   exposes candidate scores, ranks, cutoffs and selection reasons from this same search. The chunks page
   can plot stored vectors in two dimensions. That projection is for inspection. Ranking uses the original
   vectors. [Browse chunks and vectors](/knowledge/chunks).
5. **Check the mode.** In automatic mode Vercel uses keyword retrieval. A provisioned host can use the pinned
   CPU `all-MiniLM-L6-v2` encoder with compatible 384-dimensional vectors. Missing weights, a busy worker
   or a timeout leave keyword retrieval available. Builds and visitors do not need an embedding service key.
   [Park retrieval chapter](step-16.md).

## Trace a failure without reading a conversation

Activity groups events by request so you can distinguish a missing tool from a slow tool or provider.
Its summaries identify model answers, clarification replies and park briefings. A verified safety pause is
shown as a planning decision. Failed or incomplete source checks appear in Errors, including partial NPS
and NWS results and timed-out trip sections. Cached notices retain their cache label.

Performance separates those response paths and calculates model latency and token averages from agent turns.
When usage was never recorded, the page shows it as unavailable. Service timings include park retrieval,
official alerts and travel searches across the configured Axiom dataset, even after a provider is disabled.

For a traced agent request, open **View LangSmith trace** on its Activity row to see the model calls, tool
calls, nesting, durations and sanitized errors. Nimbus requires tracing, a key and both input/output privacy
settings. A signed link binds the trace to the project and Activity dataset. It expires within one hour
and within the seven-day Activity window. Deterministic intake can finish without a graph trace.
[Activity](/activity) · [Performance](/performance).

Health reports whether enabled weather dependencies and the park index are ready. Its optional Kiwi and
trivago checks discover search tools. For a failed park check, use the source-specific status in Activity
or the current notices page. A healthy tool catalog alone gives no evidence about today's notices, live
inventory, or the quality of a Gemini answer. [Health](/health) · [Park alerts](/parks/alerts).

## Verify a change

From the project directory, run the keyword retrieval cases and then the credential-free scenario replay.

```sh
uv run python -m tools.eval_parks --lexical-only
uv run python -m tools.harness run --mode replay
```

The replay fixes the clock and uses synthetic or recorded inputs, including the Dallas clarification and a
Zion conditions check. Live trials exercise a named target and record each attempt separately, including
timeouts, missing tools, provider outcomes and latency. A smoke run can help diagnose a fault. For release
review, the harness requires full passing replay and live suites, both run within the past 24 hours from a
clean checkout at the specified commit, with at least three live attempts per case against the exact preview
commit and deployment. A passing gate produces evidence for a human release decision.

A visitor can flag an answer by category. A reviewer can use that signal to write a synthetic regression
with explicit expected behavior.
[Evaluation harness and release commands](step-19.md) · [Recorded scorecards](/evaluations).
