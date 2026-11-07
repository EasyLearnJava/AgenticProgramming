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
- **Park knowledge** ships with the application. The offline builder validates the records before writing
  and replacing the SQLite index. Visitors can inspect source dates, sections and vectors directly.
  [Inspect the collection](/knowledge/sources).
- **Open-Meteo data** uses separate lifetimes in Vercel's Runtime Cache. A place lookup can be reused for 30 days,
  current weather for 10 minutes, and forecasts and air quality for 30 minutes. A cache failure falls through to an
  upstream request. [Weather cache chapter](step-7.md).
- **Current notices** use shorter, per-instance caches. A complete NPS report lasts five minutes, a failed
  or incomplete fetch one minute. NWS uses one minute for a complete point check and 30 seconds otherwise.
  Offer deduplication is scoped to a single travel turn.
- **Operational evidence** includes request references, elapsed times, outcomes and counts. The public
  Activity timeline and optional LangSmith trace expose that evidence without displaying conversation text.
  [Inspect a request](/activity).

## What happens when a dependency fails

The components have separate deadlines and outcomes. If hotels time out, a confirmed plan can still show
flights, weather and notices. An empty inventory is a different result from a provider outage. If a local
embedding query is unavailable, park retrieval can still use keywords. If an optional travel service fails
its tool-discovery check, Health shows that result separately from core weather and park-index readiness.
[Read the health report](/health).

The evaluation harness exercises these boundaries with fixed clocks, recorded provider responses and
human-authored expectations. Repeated live trials record individual failures and latency against an
identified target. Open a scorecard to see which mode, build and cases produced it.
[Evaluations](/evaluations) · [Evaluation harness chapter](step-19.md).
