# Architecture and Design

Ask “Will it rain in Paris tomorrow?” and Nimbus can show the place lookup and forecast behind its answer.
Ask “Plan a trip to Dallas” and the first useful answer is a question about dates. Ask for a weekend in Zion
and the first decision is whether conditions affect the visit. One chat supports all three.

![Nimbus: requests, evidence sources, observability and the evaluation harness](images/nimbus-system-map.svg)

[Open the full-size system map](/docs/images/nimbus-system-map.svg).

Follow the request through the upper half of the map, then follow the evaluation loop below. The model can
choose tools for an agent answer; application code can collect trip details and check park conditions directly.
Both paths expose their evidence. The harness checks behavior using repeatable cases and live trials, with
human review between visitor feedback, a new regression case and a release decision.

## How Nimbus chooses a response

| What you ask in chat | What you see | Why it works this way |
| --- | --- | --- |
| “Will it rain in Paris tomorrow?” | The weather agent can look up the place, request a forecast and stream its answer with expandable tool calls. | The forecast needs coordinates and the local date. The tool results give the model evidence for its answer. |
| “Dallas weather,” then “weather in Dallas” | An eligible fresh answer can be reused with a cache badge when caching is on. | Exact lookup precedes semantic search; browser, place, dates, units, context and freshness must still match. |
| “Plan a trip to Dallas” | A question about dates. Reply with dates and Nimbus can offer weather and the travel searches enabled here. | The city intake can collect missing details without a speculative forecast or a model call. |
| “Plan a trip to Zion” | An inline trip form with editable dates and travel details. | A park name alone gives no dates against which to check a warning or price a stay. |
| “Plan a trip to Zion this weekend from DFW” | A dated conditions briefing, or a choice if the weekend is ambiguous. | A verified park reference point and visit dates let the app check conditions before offering a travel search. |

Nimbus has curated preparation guidance for Zion, Yosemite and Grand Canyon, including selected trails. City
weather uses a global place lookup. For example, “I'm planning a trip to Dallas, Texas. Will it rain there
tomorrow?” is a weather question even though it mentions a trip. [Try these questions in chat](/).

## What builds an answer

**The browser and FastAPI** share one interface. Jinja renders the pages. HTMX inserts HTML events as a turn
progresses, so you can expand a tool call or stop a streaming reply. The browser sends a bounded conversation
history with a follow-up. Nimbus keeps the chat transcript in the page.

**The weather agent** uses Gemini through LangChain. A LangGraph loop can call several independent tools in
parallel, then give their results to the model. The four weather operations find a place, read current weather,
get a forecast and read air quality. Chat defaults to direct Open-Meteo REST without authentication. The same
weather tool definitions also power the public Nimbus MCP server. Apify-backed lanes are available when
configured. [Weather MCP tools and connection address](/health#mcp-server).

**The park briefing** uses application code to check a forecast, retrieved National Park Service (NPS)
preparation guidance, current NPS notices and active National Weather Service (NWS) alerts. This lets Nimbus
explain which check is incomplete or which warning overlaps a visit before a visitor requests prices. The
separate park trip form runs the searches a visitor confirms. [How a park trip is assembled](system-design.md).

**Optional preference memory** supplies an editable starting point across visits in the same browser. Mem0 stores
only an airport code, weather units, price currency, preparation interest and departure window that the visitor
explicitly approves. A chat request to remember something opens a preview; saving requires confirmation. The model
cannot silently write memory. Current instructions, active trip details and submitted form values take priority.
[My preferences](/preferences) provides edit, pause and forget controls.

This branch is separate from the source-retrieval and weather-cache paths in the map. It remembers how a visitor
prefers to travel, not whether a destination is safe, what a room costs or whether a flight is available. A missing
or unavailable memory service leaves the ordinary chat and planner available.

**Optional weather answer reuse** reduces repeated model work for short, ordinary weather questions. A separate
signed browser cookie owns the Qdrant partition; it does not enable preference memory. Nimbus checks an exact
fingerprint first, then asks Qdrant's hosted `sentence-transformers/all-minilm-l6-v2` model for a semantic match.
The Free model produces 384-dimensional vectors. The REST adapter adds no local Torch installation or new runtime
package. Public park retrieval uses a separate collection and never reads weather-answer cache records.

![Guarded weather answer reuse and the ordinary model fallback](images/semantic-cache-flow.svg)

Similarity is a candidate score. Independent guards check the location, request intent, dates, units, context,
browser ownership and original evidence expiry. Uncertain spelling, a changed context or a provider outage keeps
the normal answer path. Only complete successful REST weather answers can be stored, for at most 120 seconds.
An accepted hit renders new cards and a fresh answer reference without replaying past tool calls or model traces.
[Weather cache](/weather-cache) shows this browser's eligible labels, source age and remaining lifetime.
[Implementation and validation](technical-details.md#follow-a-weather-cache-hit).

## Where the evidence comes from

- **Weather and air quality** come from weather tools. The place, forecast dates and available hours constrain
  what the answer can say. A current observation and a forecast cover different times.
- **Preparation advice** comes from a versioned SQLite collection built from official NPS pages. Each passage
  retains its source, section and destination. Optional Qdrant-hosted MiniLM ranks public chunk IDs alongside
  local BM25; reciprocal rank fusion combines their ranks. Text and citations still come from SQLite. Both
  branches share destination and season restrictions, and a provider outage leaves a visible BM25 fallback.
  Follow the actual terms, scores and final ranks in [Retrieval Playground](/knowledge/retrieval), then inspect
  BM25, semantic and fusion timings in the Activity trace. [Source documents](/knowledge/sources) ·
  [Chunks and vectors](/knowledge/chunks).
- **Notices and warnings** come from separate live services. A park-wide NPS closure and an NWS warning for a
  particular point can have different geographic and time boundaries. You can also check current NPS notices
  for a park directly. [Park alerts](/parks/alerts).
- **Travel options** come from Kiwi for flights and trivago for hotels when each integration is enabled. The
  adapters validate dates, prices and provider links before displaying offers. Booking and payment happen with
  the provider. [Flight and hotel search](step-18.md).

## How to check an answer

Start with the tool chips in chat to see what ran. On Vercel, the CDN serves static assets and one Python
function serves FastAPI routes. Request middleware attaches a request ID to structured events. When configured,
Axiom stores those events and a separate read credential lets Activity and Performance display them. Sentry can
receive sanitized errors. LangSmith adds model and tool timings to eligible Activity rows when tracing is enabled.
[Activity](/activity) · [Performance](/performance).

Activity distinguishes cached answers from agent answers and records cache hits, misses, bypasses and failures.
A cache hit has no new Gemini or weather-tool execution, so its timeline explains the absence of a model trace.
The private inventory shows normalized labels and expiry metadata, while public Activity never shows cached text.

Evaluations shows how the app performed on synthetic questions, including repeated trials and failures.
Health reports dependency readiness separately from answer quality. [Evaluations](/evaluations) · [Health](/health).

The harness keeps offline replay and live attempts separate. Its scorecards preserve failed attempts, and its
release evidence check ties complete, repeated evaluation to the specified commit and preview deployment.
Feedback supplies a category and answer reference; a reviewer writes a synthetic park-intake case before
promoting it into the regression suite. This process adds a test, without training the model or automatically
deploying the app. [Follow the harness loop](step-19.md).

For the functions that choose a route, rank a passage and build an offer card, see
[Technical details](technical-details.md).
