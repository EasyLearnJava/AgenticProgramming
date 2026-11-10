# System Design

A visitor flying from Dallas to Zion needs several answers. Will the park weather cover the visit dates?
Does a closure affect the whole park or one trail? Are the available rooms near the park or near the airport?
Nimbus keeps those questions separate so each answer can show its source, date and limitations.

![Nimbus system map: runtime data flow, source retrieval and the reviewed evaluation loop](images/nimbus-system-map.svg)

[Open the full-size system map](/docs/images/nimbus-system-map.svg).

The map separates the live request path from the harness that checks it. Agent reasoning, direct trip logic,
stored preparation guidance and current alerts have different jobs; the arrows show where they meet.

## From a weekend request to a decision

![How a dated park request becomes a conditions briefing and an optional travel search](images/system-design.svg)

1. **Establish the trip.** In chat, a supported park planning request can carry a park or trail, origin,
   dates, party and travel preferences. For “this weekend from DFW,” the date parser can use the departure
   airport's time zone. A full weekend normally spans Friday through Sunday, with editable evening flight
   preferences. During the weekend Nimbus can offer the remaining days or the following weekend. Missing dates
   or an uncertain destination prompt a choice.
   When enabled and approved, saved preferences fill missing defaults before date interpretation. A saved DFW origin
   therefore uses the Dallas calendar near midnight. An explicit BOS origin uses Boston instead; driving and flight
   opt-outs do not become flight requests because an airport was saved.
2. **Check four sources in parallel.** The dated chat briefing looks up the forecast for a named park reference
   point, retrieves preparation passages, checks current NPS notices and requests active NWS alerts at that
   point. A forecast can cover only part of a stay. An active alert has its own start and end times. The park's
   time zone determines whether it overlaps the visit.
3. **Explain what changes the plan.** A verified whole-park closure affecting the dates or an overlapping
   severe or extreme weather warning pauses the itinerary and hides the quote controls. A trail closure can
   prompt an adjustment. Missing forecast coverage, an incomplete official check or uncertain timing can
   prompt a review with a tentative itinerary. When the checks find no major disruption, the briefing still
   asks the visitor to recheck conditions before departure.
4. **Search when the visitor asks.** The eligible search controls let the visitor confirm or edit the trip.
   Kiwi searches flights to a gateway, while trivago searches stays near the park. A driving trip skips
   flights. A trip with no remaining overnight stay skips hotels. A listed fare or room price can change
   before the visitor completes a booking with the provider.

The standalone **Plan a park trip** form is another entry point. It appears when park guidance and at least
one travel provider are enabled. On submission, it builds up to five independent sections for flights, hotels,
weather, preparation and NPS notices. The NWS decision described above belongs to the **chat briefing**.
[Park trip planning chapter](step-18.md).

## What each source can tell you

| Source | What Nimbus uses | How to interpret it |
| --- | --- | --- |
| Selected weather lane (Open-Meteo by default) | Dated forecasts at a registry reference point such as Zion Canyon or the Grand Canyon's South Rim. | Check the point and covered dates. Weather can differ higher on the trail. |
| Published NPS guidance | Reviewed sections from official pages, stored in a versioned index with source links. | Useful for preparation such as flash-flood awareness. It describes a published risk, independent of today's warnings. |
| NPS Alerts API | Park notices, categories and official links, fetched with a server-side key. | A road closure may affect only that road. An empty or unavailable check gives no assurance about access. |
| NWS active alerts | Warnings and other active alerts for the reference coordinates. | A severe warning matters to the decision when its active interval overlaps the visit. Future warnings may still be issued. |
| Kiwi and trivago | Structured, read-only offer searches using the visitor's permitted trip details. | Check travel dates, currency, the flight party total, and whether a hotel price is nightly or for the stay. |

## Where data lives and how long it lasts

- **Chat history** lives in the browser page. Follow-ups send bounded prior text to Nimbus. Agent turns send
  the question and relevant conversation to Gemini. Flight and hotel providers receive structured search
  fields such as places, dates and party size.
- **Approved travel preferences** live in Mem0, behind an opaque signed browser cookie. The cookie holds a random
  scope, expiry and mode, not preference values. Five typed fields are allowed: airport, weather units,
  currency, preparation interest and departure window. No accounts or cross-device linking are implemented. Anyone
  using the same browser profile can manage its preferences. New chat does not clear them.
- **Park knowledge** lives in a dedicated Qdrant collection: approved text, provenance, a native BM25 text index
  and hosted MiniLM dense vectors. Text-only preparation preserves reviewed section and season boundaries.
  Publication generates each vector once per generation and verifies text, vectors and the readiness marker.
  The app bundles only destination metadata and expected record hashes, then reads actual passages from Qdrant.
  Both searches share park, destination, season and version filters; Nimbus fuses ranks and bounds the context.
  Hosted requests send search text without attaching history or preferences. A semantic-only failure can use
  successful Qdrant BM25; a full outage makes guidance unavailable. [Inspect the collection](/knowledge/sources) ·
  [Inspect ranking and traces](technical-details.md#reproduce-a-park-retrieval).
- **Open-Meteo data** uses separate lifetimes in Vercel's Runtime Cache. A place lookup can be reused for 30 days,
  current weather for 10 minutes, and forecasts and air quality for 30 minutes. A cache failure falls through to an
  upstream request. [Weather cache chapter](step-7.md).
- **Optional weather answers** live in Qdrant, partitioned by a separate signed one-day browser cookie. Eligible
  weather text goes to hosted MiniLM inference; the stored record includes Markdown, typed source evidence,
  context fingerprints, absolute expiry and an integrity signature. Reuse lasts at most 120 seconds, capped by
  the original source expiry and both visitor and destination midnight. A hit never extends that deadline.
  [This browser's answer cache](/weather-cache).
- **Current notices** use shorter, per-instance caches. A complete NPS report lasts five minutes, a failed
  or incomplete fetch one minute. NWS uses one minute for a complete point check and 30 seconds otherwise.
  Offer deduplication is scoped to a single travel turn.
- **Operational evidence** includes request references, elapsed times, outcomes and counts. The public
  Activity timeline and optional LangSmith trace expose that evidence without displaying conversation text.
  [Inspect a request](/activity).

Preferences and the browser link expire 180 days after saving. Expiry excludes them from normal use, but is not a
guarantee of physical deletion at Mem0. **Pause** stops their use while retaining them. **Forget** deletes the owned
Nimbus records, including expired records, then reads back to confirm absence. If confirmation fails, preference use
stays off and the cookie is retained so deletion can be retried. Clearing the cookie first can lose that access.
[Manage saved preferences](/preferences).

Only the approved typed profile is sent to Mem0; no automatic conversation extraction runs. A usable profile may be
included as default values in Gemini's answer context. Memory is separate from trip dates, guests, payment details,
forecast or alert evidence, prices and booking permission. Weather units are an independent choice from browser
locale and currency, so Celsius with USD is supported throughout the park briefing and confirmed plan.

## Reuse an answer without inventing a new tool run

![Weather-cache guards, Qdrant lookup and the normal answer path](images/semantic-cache-flow.svg)

An exact match avoids an embedding request. Otherwise the cache compares hosted MiniLM vectors with cosine
similarity, inside mandatory browser, context and request-policy filters. The application checks the stored
record's signature, scope and expiry again. A high similarity score cannot cross a date, unit or location boundary.
Authenticated history receipts allow repeated weather questions in the same conversation; an altered history or
a prior turn under another policy falls through to the existing agent.

The cached answer is rendered anew from Markdown and typed weather evidence. It receives a new turn ID, feedback
reference and cache badge; the UI does not replay old tool timings. In `shadow` mode the same lookup measures matches
while Gemini continues to answer. `off` makes no cache network calls, and `on` permits verified reuse.

Expiry is checked on every read, independent of physical deletion. A later store opportunistically removes expired
records, including older cache versions; an idle cluster can retain expired data until another store or operator
cleanup. The setup command applies Qdrant strict limits of 2,000 points and 120,000,000 payload bytes. A separate
application count check avoids avoidable writes near capacity; it is not the concurrent enforcement mechanism.
The database limits remain authoritative across Vercel instances.

The [Weather cache page](/weather-cache) lists at most 50 active entries for this browser, with source-data age and
expiry as of the latest refresh. It exposes no original questions, generated answers, vectors or preference values.
Its response is never publicly cached. Clearing the browser cookie loses access to that short-lived inventory.
This cache is an optimization, not long-term history or a memory service.

## What happens when a dependency fails

The components have separate deadlines and outcomes. If hotels time out, a confirmed plan can still show
flights, weather and notices. An empty inventory is a different result from a provider outage. If hosted dense
search fails, successful Qdrant BM25 can still answer; a full Qdrant outage cannot. If an optional travel service fails
its tool-discovery check, Health shows that result separately from core weather and park-index readiness.
[Read the health report](/health).

Mem0 failures, conflicting records and uncertain writes cannot supply defaults. An unconfirmed save pauses memory
use; a failed read continues from the current request. A fresh read and revision check precede a save, followed by
readback verification. Mem0 does not provide a transaction spanning those operations: stale forms and observed
duplicates are rejected, but truly simultaneous updates on separate server instances can still be last-write-wins.
This is not transactional cross-tab editing.

Qdrant timeouts, refusals, malformed records and quota failures become cache misses, not failed chat answers.
The cache viewer distinguishes an unavailable inventory from an empty one. Cache operations have their own Activity
events; cached completions are counted separately from model latency and token usage. No cached question or answer
text is placed in logs or LangSmith.

The evaluation harness exercises these boundaries with fixed clocks, recorded provider responses and
human-authored expectations. Repeated live trials record individual failures and latency against an
identified target. Open a scorecard to see which mode, build and cases produced it.
[Evaluations](/evaluations) · [Evaluation harness chapter](step-19.md).
