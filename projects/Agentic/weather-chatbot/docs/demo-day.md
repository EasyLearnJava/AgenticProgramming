# DemoDay

Show fresh weather, exact reuse, semantic reuse and city isolation in five prompts.

**Set up:** use a fresh private browser window with caching enabled in `on` mode and LangSmith tracing enabled.
Open [Chat](/), then [Activity](/activity) and [Weather cache](/weather-cache) in separate tabs in that window.
Keep the same chat and units. Wait for each request to finish, then send the next prompt promptly:
entries last **at most two minutes**, sometimes less. New chat alone does not clear the cache.

## 1. Ask Dallas for the first time

`Dallas weather`

No saved match: Gemini uses the weather tools and Nimbus saves the answer if its weather evidence is complete.
**Activity:** “No reusable answer” → “Answer saved”.
**Trace:** cache lookup → agent/model and weather calls → cache store, with Qdrant cleanup, count and save.

## 2. Repeat exactly

`Dallas weather`

The fresh answer is reused without calling Gemini or the weather tools.
**Activity:** “Exact match”. **Trace:** lookup → Qdrant exact match, outcome **Exact hit**.
There is still a new request trace, but no model call or similarity search.

## 3. Change the wording

`What is the weather in Dallas?`

The exact text differs; semantic search can reuse the Dallas answer.
**Activity:** “Similar question matched”. **Trace:** exact miss → Qdrant similarity search.
Select that call to see **Similarity hit**, score and cutoff (normally **0.80**).
Reuse requires the cutoff and all location, units, context and freshness checks to pass.

## 4. Switch cities in the same chat

`Vizag weather`

Dallas must not be reused for another city. Expect a new weather answer and a separate saved entry.
**Activity:** “No reusable answer” → “Answer saved”. **Trace:** model/weather calls and cache store.
**Weather cache:** refresh to see **Visakhapatnam**, Vizag’s approved city name.

## 5. Use the city's other name

`Visakhapatnam weather`

Nimbus recognizes Vizag and Visakhapatnam as the same city and can reuse that fresh answer.
**Activity:** “Similar question matched”. **Trace:** similarity search with **Similarity hit** and its score.
The alias makes the location checks agree; the cache does not guess that unrelated cities are equivalent.

## Show the evidence

In [Activity](/activity), open the newest request and choose **View LangSmith trace**.
Match requests by time, order and reference; prompts stay private. Use **Refresh trace** if it is still arriving.

If a step misses, check [Weather cache](/weather-cache) for expiry and the trace for **Not reusable**, **Bypassed**
or **Error**. A semantic match is expected, not guaranteed; a miss falls back to a fresh answer.
After an entry expires, asking again uses Gemini and the weather tools; valid provider-cache data may still be reused.
