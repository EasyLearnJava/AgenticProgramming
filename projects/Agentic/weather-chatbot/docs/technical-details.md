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
2. **Choose the execution path.** `chat()` recognizes explicit memory-management requests and loads usable approved
   preferences. It then checks park planning intent, city trip intake, missing hotel dates and requests beyond
   the forecast horizon before accessing Gemini. A city dates-only follow-up can reuse
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

Completed weather calls also feed `nimbus/weather_cards.py`. It validates the tool JSON and groups results by
coordinates, destination time zone and returned units. The chat shows current conditions, feels-like temperature,
wind, daily highs and lows, precipitation probabilities, daylight details and up to six upcoming hourly samples.
Every requested daily forecast remains available. A city heading comes only from matching geocoded coordinates;
without that match, the heading names the coordinates. Missing measurements remain unavailable, rather than zero.

`templates/weather_cards.html` and `/static/weather-cards.css` render these measurements separately from the model's
**Summary & context**. The original prose stays in `.answer`, so chat history and evaluation graders do not receive
duplicate card labels or values. The cards show the observation time, destination time zone, forecast check time,
source and cache status. Forecast check time is the tool's local reference time, not a forecast issuance time.
Failed tools do not create cards; successful weather can still appear alongside a later model error.

The offline regressions in `tests/unit/test_weather_cards.py` cover missing values, dates, daylight, city and unit
separation, malformed results and escaping. `tests/e2e/test_weather_cards.py` exercises the real streamed chat with
synthetic weather, follow-up history, phone layouts and accessibility. Run the corresponding evidence mutations with
`python tools/mutation_check.py --weather-cards`.

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

## Follow an approved preference

Mem0 is an optional preference store. It does not replace the park index, forecast cache or LangGraph agent.
Nimbus reads one typed profile for the current browser scope; it does not perform semantic search over conversation
history. The implementation uses bounded HTTP calls through `httpx2`, with no additional embedding model or Mem0 SDK
in the deployed function.

| Boundary | Code | What it enforces |
| --- | --- | --- |
| Allowed values | `memory/models.py: PreferenceProfile` | One three-letter airport code; metric or imperial units; USD, CAD, EUR or GBP; easy hikes, hiking, sightseeing or camping; morning, evening or by-noon departure. Every field can be unset. Extra fields are rejected. |
| Explicit approval | `memory/intake.py`, `memory/routes.py`, `templates/preference_form.html` | “Remember…” produces an editable preview. Only a validated save form with consent writes the selected fields. The model has no save tool. |
| Browser ownership | `memory/identity.py` | A signed, expiring HTTP-only cookie carries a random scope, mode and expiry. Forms have short-lived scope-bound tokens; mutations also require the same origin. Submitted record or user IDs cannot select another profile. |
| Provider ownership | `memory/client.py` | A fixed Mem0 host, bounded responses and pagination, owner metadata checks, supported schema and one canonical profile. Foreign, invalid or duplicate records do not become defaults. |
| Honest writes | `Mem0Service.save()` and `forget()` | Check the expected revision before saving, then verify values by reading them back. Delete only discovered owned records and confirm absence. A write acknowledgement alone is not success. |
| Optional request context | `memory/context.py` | Only an active browser identity and a ready snapshot supply defaults. Disabled, paused, conflicting and unavailable states leave the current request in control. |
| Trip precedence | `travel/preferences.py`, `planner_intake.py` | Current parsed instructions and explicit details of the active trip precede stored defaults. Apply the origin before local weekend dates; preserve driving and service opt-outs. Initial form prefill never overwrites submitted fields. |
| Independent units | `travel/park_forecast.py`, `BriefPreferences`, `ParkTrip` | Carry the chosen unit system through the briefing and confirmed plan. Use browser locale only when units are unset; keep currency separate. |

The five fields are serialized as JSON, with inference disabled when adding a Mem0 record. Nimbus sends neither
the full conversation nor an automatic summary to Mem0. An approved profile may enter the agent's context as defaults,
with an instruction that current details take precedence. The deterministic park intake uses the same typed values
directly. A saved preference never approves a flight or hotel search, changes a date already submitted, or supplies
evidence that a park is open or safe.

Open [My preferences](/preferences) to review, edit, pause or forget this browser's profile. It has no account recovery
or cross-device synchronization. A shared browser profile is shared access. Both the cookie and the stored record
receive a 180-day expiry from saving; expiry prevents normal use, but is not confirmed physical deletion. Forget
includes expired owned records. If deletion is uncertain, Nimbus keeps use disabled and retains the scope for a retry.
Clearing cookies before deleting can lose access to those records. New chat clears only conversation history.

Memory pages and responses use private, no-store caching. `memory.operation` events contain only action, bounded
status/reason and elapsed time under the normal request reference. They omit preference values, owner and record IDs,
cookie contents, credentials and provider response bodies. Chat prompts and memory values are not logged or exposed
in public Activity. LangSmith input/output hiding continues to apply to agent context.

For local setup, use `MEMORY_ENABLED`, `MEM0_API_KEY` and `MEMORY_COOKIE_SECRET` in ignored `.env.local`; the example
file contains placeholders. See [the hosted configuration checklist](waiting-on-you.md#mem0-travel-preferences).
The offline coverage lives in `tests/unit/test_memory_client.py`, `tests/unit/test_memory_travel.py` and
`tests/e2e/test_memory_preferences.py`. It exercises owned-profile handling, provider failures, preference precedence,
date boundaries and the browser controls without requiring a real visitor's stored preferences.

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

The **Memory** tab at [Activity](/activity?show=memory) shows reads, saves, pause/resume and deletion outcomes, plus
chat previews. Its timeline keeps action, status, bounded failure reason and timing; preference values, browser
identifiers and provider record IDs are excluded. A preview is clearly distinguished from a confirmed save.

The offline harness includes six preference regressions in `evals/harness/memory-defaults.json`: saved-airport
calendar boundaries, explicit overrides, active-trip precedence, driving, unrestricted departure and ordinary
weather. Run `python -m tools.mutation_check --memory` to prove the consent, ownership, expiry, deletion and logging
guards fail when deliberately broken. Provider and browser tests cover persistence and failure paths separately.

Activity groups events by request so you can distinguish a missing tool from a slow tool or provider.
Its summaries identify model answers, clarification replies and park briefings. A verified safety pause is
shown as a planning decision. Failed or incomplete source checks appear in Errors, including partial NPS
and NWS results and timed-out trip sections. Cached notices retain their cache label.

Performance separates those response paths and calculates model latency and token averages from agent turns.
When usage was never recorded, the page shows it as unavailable. Service timings include park retrieval,
official alerts and travel searches across the configured Axiom dataset, even after a provider is disabled.

For a traced agent request, open **View LangSmith trace** on its Activity row to see the model calls, tool
calls and their parent-child relationships in the trace explorer. Summary cards show the agent's elapsed time
and displayed model/tool span counts. The waterfall uses a common time axis; nested durations overlap and must
not be added together. Filter by call type or errors, search call labels, collapse a branch, or select a call
for exact timings and its parent. These controls operate in the browser without another LangSmith request.

Only the existing sanitized operational fields reach this view: no prompts, outputs, credentials, token counts
or costs are added. Nested tool spans remain separate records; a repeated name is not necessarily another
external API request. A partial trace is labeled, and unknown durations remain unknown. Access still uses the
same privacy settings and signed, bounded read path described below.

The reader restricts the trace to the configured project. Nimbus requires tracing, a key and both input/output
privacy settings. A signed link binds the trace to the project and Activity dataset. It expires within one hour
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
