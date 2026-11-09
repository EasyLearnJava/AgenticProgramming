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
   forecast horizon is 16 days, and hourly output covers up to three days. Eligible ordinary weather questions
   can check the optional answer cache before constructing the agent; this specific rain question is excluded.
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

## Follow a weather cache hit

The answer cache is separate from Open-Meteo's provider cache and from Mem0 preferences. When enabled, a short
question such as “Dallas weather” first checks an exact fingerprint, then a semantic candidate from Qdrant.
There is no Gemini call just to decide whether two questions match. Eligibility and independent request guards
must also agree; a semantic score alone cannot authorize reuse.

![Weather answer reuse with independent guards and normal fallback](images/semantic-cache-flow.svg)

| Responsibility | Code | Invariant |
| --- | --- | --- |
| Eligible request | `semantic_cache/policy.py`, `integration.py` | Short explicit single-place English weather overviews on REST without auth. Memory commands, trips, park guidance, alerts, safety advice, unknown context and other lanes retain their existing paths. |
| Browser and history | `semantic_cache/identity.py`, `integration.py` | A signed HTTP-only cookie lasts one day. Authenticated weather turns may switch unqualified cities while retaining units and time intent. Changed qualified locations, other constraints or altered history bypass reuse. |
| Candidate lookup | `semantic_cache/service.py` | Exact lookup before hosted MiniLM; both require matching browser, context and policy filters. Locally recheck record integrity, ownership, expiry and score. |
| Successful admission | `semantic_cache/evidence.py`, `chat.py` | Only complete successful geocoding and ordinary weather evidence is stored. Reject ambiguous destinations, mismatched coordinates or units, missing required forecast coverage, duplicate calls, tool errors and partial model output. |
| Original data age | `open_meteo.py`, `tools.py` | Versioned provider-cache envelopes carry original fetch and expiry times through tool records. Old entries without valid freshness metadata are fetched again. |
| Output and inventory | `weather_cards.py`, `semantic_cache/page.py` | Re-render typed evidence and safe Markdown with new turn IDs. The private page lists normalized labels, source age and expiry; it never shows raw question or answer text. |

Qdrant's hosted `sentence-transformers/all-minilm-l6-v2` produces 384-dimensional dense embeddings. The dedicated
collection uses cosine distance. The existing asynchronous `httpx2` dependency calls Qdrant's REST API with the
key in an `api-key` header, bounded response sizes and timeouts. No Qdrant SDK, Torch or local embedding model is
added to the Vercel runtime. The hosted model is available on Qdrant Free; its availability and limits remain
provider-controlled. [Qdrant inference documentation](https://qdrant.tech/documentation/cloud/inference/).

The default semantic cutoff is `0.80`, a measured candidate threshold, not a confidence guarantee. Browser scope,
place spelling and qualifiers, overview/current/today intent, calendar date, units, locale and time zone remain
independent requirements. Context fingerprints cover the prompt contract, model, build, enabled features and
preference revision/mode. Unrecognized place spellings and unsupported wording fall back safely rather than
guessing that two nearby vectors refer to the same city.

The approved alias `Vizag` resolves to `Visakhapatnam` in both the location guard and embedding input; explicit
region/country qualifiers remain required. Dallas and Vizag occupy separate entries, and a signed conversation
can switch between them. General weather validates forecast coverage against the destination's current date.
Explicit “today” retains the browser date defined by the prompt and requires that date in the returned forecast.
Neither case can reuse an answer beyond either time zone's midnight.

A completed eligible weather turn receives its signed history receipt even when its evidence is not stored.
The receipt authenticates the conversation, not the weather data. This lets a later eligible city question cache
normally after an incomplete result; failed or cancelled streams and altered history still cannot mint receipts.
Conversations already missing a receipt from an older build need New chat once; unsigned history is never trusted
retroactively.

The cache deadline is the earliest of save time plus 120 seconds, each original provider expiry, and midnight in
the visitor and destination time zones. Reading a hit never renews it. The page rechecks expiry when rendering;
remaining seconds are a snapshot at refresh. Expired points can remain physically stored while idle. Later stores
opportunistically delete expired entries across cache versions, while read-time checks always prevent reuse.

The record contains Markdown, validated weather evidence and minimal policy metadata under an opaque browser scope.
An HMAC protects integrity; it does not encrypt the stored record. Eligible weather text is sent to Qdrant for
embedding, and the provider stores its vector and answer payload. Full chat history is not sent to Qdrant.
Questions, answers, vectors, scopes, preferences and keys are absent from application logs and LangSmith traces.
The browser cookie is separate from Mem0 consent; sharing a browser profile also shares its cache inventory.

Three deployment modes make rollout explicit: `off` makes no cache network calls; `shadow` records matches while
the normal agent still answers; `on` allows accepted hits to bypass Gemini and weather tools. A hit has a fresh
feedback reference and a “Cached answer” badge. Activity records `workflow=cached` and cache operation outcomes,
with an explicit explanation that no new LangSmith model trace was created. It does not replay previous traces.
Timeouts, malformed records, refusals, quota limits and failed writes leave the normal answer flow available.

### Configure and validate answer reuse

Set `QDRANT_URL` and `QDRANT_API_KEY` only in ignored `.env.local` for local work. `SEMANTIC_CACHE_MODE` defaults to
`off`; start with `shadow`. `QDRANT_COLLECTION` defaults to `nimbus_weather_cache`, and the threshold is optional
configuration. Runtime access needs only the dedicated collection; the setup command needs collection-management
permission. Key rotation invalidates existing cache signatures and browser scopes, which can safely expire.

```sh
uv run python -m tools.setup_semantic_cache
uv run pytest tests/unit -k semantic_cache
uv run pytest tests/e2e -k semantic_cache --browser-channel chrome
uv run python -m tools.eval_semantic_cache --cases evals/semantic_cache.json
uv run python -m tools.eval_semantic_cache --cases evals/semantic_cache_heldout.json
```

The setup command creates or verifies a compatible collection without replacing it, applies six filter indexes,
and enables Qdrant strict limits of 2,000 points and 120,000,000 payload bytes. A count admission check reduces
unnecessary writes; the server-side strict limits enforce capacity across simultaneous Vercel instances.

Mock-provider tests prove adapter behavior, expiry, ownership, history integrity, fallback and rendering. Chrome
tests cover the real form/history flow, cache badges, private inventory, phone layouts and accessibility. Those
tests do not establish the real embedding model's recall. Live evaluations use a separate `_eval` collection and
random synthetic scope, remove their own fixtures and report exact reuse, cross-browser isolation, false hits,
provider errors and positive recall separately. An unavailable run is not a pass. Inspect the JSON artifact and its
case IDs before enabling reuse. A case used to improve normalization becomes regression evidence, not a new held-out
test; the initial report remains available.
[Hosted settings and validation](waiting-on-you.md#qdrant-weather-answer-cache).

### Local validation on 9 November 2026

Local mode is `on` after these checks. The running local app and `/weather-cache` returned HTTP 200; the inventory
response uses `Cache-Control: no-store`. Vercel settings and an exact hosted-build check are still pending.

- **Unit and mutation checks:** all 2,021 unit tests passed in 72.25 seconds. All 12 cache mutations were caught,
  including the original-evidence-expiry guard added after the first mutation exposed a missing assertion.
- **Browser and harness regressions:** all 226 Chrome tests passed, including accessibility and responsive layouts.
  The offline harness replay passed 455 cases: 10 golden, 41 park, 4 provider, 7 red-team, 1 regression and 392 weekend
  cases. Replay exercises recorded or synthetic behavior; it is not three repeated live model trials.
- **Real hosted embeddings:** at the measured `0.80` threshold, the final normalized evaluation passed 18 cases,
  exact reuse and cross-browser isolation, with zero false hits, zero provider errors and positive recall `1.0`.
  Repository artifact: `evals/semantic-cache-last-run.json`.
- **The initial independent set exposed a limitation:** the frozen `0.80` run recalled 3 of 5 positive examples
  (`60%`). The original `evals/semantic-cache-heldout-run.json` is preserved. General normalization of question
  politeness and the approved `wether` spelling improved the same set to 10/10 overall. Place names, dates and units
  are unchanged. The refined `evals/semantic-cache-refined-run.json` is regression evidence; those examples are no
  longer an untouched held-out set.
- **Real chat smoke:** “Dallas weather” used Gemini and three weather tools, then stored a complete answer.
  “Weather in Dallas” in the same conversation produced `semantic_hit`, `workflow=cached` and zero tool calls,
  without another Gemini call. The private inventory returned HTTP 200 with entries.
  Sanitized repository artifact: `evals/semantic-cache-live-chat.json`.
- **Two independent reviews:** the resulting fixes preserve original source age, bind reuse to the prompt build
  and qualified history policy, require complete hourly/daily coverage, clean expired records across versions and
  count provider failures separately in evaluations. A mutation also exposed a missing original-evidence-expiry
  assertion; the regression now covers it.

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
status/reason, elapsed time and, when traced, a fresh operation trace ID under the normal request reference.
They omit preference values, owner and record IDs,
cookie contents, credentials and provider response bodies. Chat prompts and memory values are not logged or exposed
in public Activity. LangSmith input/output hiding continues to apply to agent context.

`memory/tracing.py` records independent `mem0.read`, `mem0.save` and `mem0.delete` tool roots using the existing
configured LangSmith client. Only empty inputs/outputs and fixed operation status/reason metadata are sent;
exception details and provider bodies are never attached. Each duration includes ownership checks and readback
verification. An empty read is successful; an unavailable, conflicting or unconfirmed operation is failed. A trace
write failure cannot change the preference operation, and cancellation still closes the trace safely. Uploads use
the SDK's existing background queue and bounded Vercel flush. A queued trace can take a moment to become readable.

In **Activity → Memory**, open the labeled read, save or delete trace. The explorer shows a Memory operation,
its duration and status, with zero model calls. A memory read and a later chat agent have separate links on the same
request: the read precedes the graph, while preference saves and deletions use their own HTTP requests. Internal
readback checks are part of the save/delete span, not extra user read operations. Pause is a local control and makes
no Mem0 call; resume traces its verification read. Tracing disabled means no memory trace is created, and old entries
are not backfilled. The existing LangSmith privacy settings and Activity query credential remain required.

For local setup, use `MEMORY_ENABLED`, `MEM0_API_KEY` and `MEMORY_COOKIE_SECRET` in ignored `.env.local`; the example
file contains placeholders. See [the hosted configuration checklist](waiting-on-you.md#mem0-travel-preferences).
The offline coverage lives in `tests/unit/test_memory_client.py`, `tests/unit/test_memory_travel.py` and
`tests/e2e/test_memory_preferences.py`. It exercises owned-profile handling, provider failures, preference precedence,
date boundaries and the browser controls without requiring a real visitor's stored preferences.

Trace coverage adds `test_memory_tracing.py` (actual SDK serialization, private-data canaries, safe failures and
project fallbacks), `test_memory_trace_routes.py` (real save/read/chat/delete requests), Activity linkage tests and
the Chrome trace explorer checks. Local validation on 9 November 2026 passed 1,810 unit tests, 18 Chrome trace and
preference tests, all 22 trace mutation checks, Ruff and strict mypy. Two independent reviewers rechecked the project
fallback correction and reported no remaining actionable findings. Hosted LangSmith delivery was not verified:
no local LangSmith credential was configured, and this validation did not deploy the changes.

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
Its summaries identify model answers, cached weather answers, clarification replies and park briefings. A safety pause
is shown as a planning decision. Failed or incomplete source checks appear in Errors, including partial NPS
and NWS results and timed-out trip sections. Cached notices retain their cache label. Optional answer-cache failures
also remain visible, even when the ordinary model answer succeeds.

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
An independently traced Mem0 lookup can still be linked on that request. Memory trace roots must match one of
the three exact operation names and the tool run type; arbitrary LangSmith roots remain withheld.
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
