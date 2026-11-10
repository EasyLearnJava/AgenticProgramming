# DemoDay

A live walkthrough of Nimbus, in parts. Each part is a few prompts to type and what to show after each one.

## Part 1 · The weather answer cache

Five prompts show a fresh answer, an exact repeat, a reworded question, a new city and that city's other name.
The first time, Gemini and Open-Meteo answer and Nimbus saves the result. After that, a question that means the
same thing, from the same browser, gets the saved answer back without calling Gemini.

[![One weather question, two ways to answer it: the components each DemoDay prompt passes through](images/demo-day-cache-flow.svg)](images/demo-day-cache-flow.svg)

*Every prompt starts at step 1 and leaves at the first path it takes; the pills show which prompts take which
path. Select the diagram to open it full size.*

### The five prompts at a glance

| # | Type this | What happens | Activity shows |
|:-:|---|---|---|
| 1 | `Dallas weather` | A fresh answer, then saved | No reusable answer → Answer saved |
| 2 | `Dallas weather` | The same words: reused | Exact match |
| 3 | `What is the weather in Dallas?` | Other words, same meaning: reused | Similar question matched |
| 4 | `Vizag weather` | A new city: a fresh answer, saved apart | No reusable answer → Answer saved |
| 5 | `Visakhapatnam weather` | Vizag's other name: reused | Similar question matched |

### Before you start

- **Settings:** the deployment has the weather answer cache in `on` mode and LangSmith tracing enabled.
- **Tabs:** in one fresh private window, open [Chat](/), [Activity](/activity) and [Weather cache](/weather-cache).
  A private window has no saved preferences, so step 1 makes no Mem0 call.
- **Pace:** a saved answer is reusable for **two minutes at most**, sometimes less. Before each prompt, wait until
  **Send** comes back in place of **Stop**: the answer shows first, then Nimbus saves it, and a prompt sent during
  the save is dropped.
- **One chat, only these prompts:** earlier turns go back with each question, signed, and a city may change but
  units and timing may not. If you ask anything else, choose **New chat** before going on. New chat alone doesn't
  clear the cache.
- **Activity runs a minute behind:** its page is kept for a minute, so a request can take that long to appear.
  Refresh it after a minute, or show it after a pair of steps.
- **No deploys:** answers saved before a deploy of new code are never reused, so don't deploy during the demo.

### Step 1 · Ask about a city for the first time

> `Dallas weather`

Nothing is saved yet, so Gemini calls the weather tools and Nimbus writes a fresh answer. Once you have the whole
answer, Nimbus checks its weather evidence and saves it.

- **Activity:** "No reusable answer", then "Answer saved".
- **Trace:** cache lookup (Qdrant exact match, then similarity search, both **Miss**), the agent with its Gemini and
  weather calls, then cache store (remove expired, count, save).

### Step 2 · Repeat it exactly

> `Dallas weather`

The same words match the fresh saved answer, so it comes back without Gemini or the weather tools. The answer says
"Cached answer · Gemini was not called" and how many seconds it has left.

- **Activity:** "Exact match".
- **Trace:** lookup, then Qdrant exact match with outcome **Exact hit**. It's a new request trace, but with no model
  call and no similarity search.

### Step 3 · Change the wording

> `What is the weather in Dallas?`

The words differ, so the exact match misses, and the similarity search finds the Dallas answer.

- **Activity:** "Similar question matched".
- **Trace:** exact match **Miss**, then Qdrant similarity search, whose row shows **Similarity hit**, the score and
  the cutoff (**0.800** by default).

Similarity alone never reuses an answer: the place, units, timing and context must match too.

### Step 4 · Switch cities in the same chat

> `Vizag weather`

Qdrant searches only answers for the same place, so the Dallas answer is never a candidate. Expect a fresh answer
and a second saved entry.

- **Activity:** "No reusable answer", then "Answer saved".
- **Trace:** exact match **Miss** and similarity search **Miss** with no score, then the model and weather calls,
  then cache store.
- **Weather cache:** refresh it to see an entry for **Visakhapatnam**, the name Open-Meteo gives Vizag.

### Step 5 · Use the city's other name

> `Visakhapatnam weather`

Nimbus knows Vizag and Visakhapatnam are one city, so this reuses the Vizag answer.

- **Activity:** "Similar question matched".
- **Trace:** exact match **Miss**, because the words differ, then **Similarity hit** with a score near **1.000**:
  Vizag becomes Visakhapatnam before the search, so both questions are searched as the same words.

Only approved names count as the same city; Nimbus never guesses that two different names mean one place.

### Show the evidence

In [Activity](/activity), open the newest request and choose **View LangSmith trace**. Match requests by their
time, order and reference; prompts stay private. If the trace is still arriving, choose **Refresh trace**.

### If a step misses

- **"Answer not reusable":** the words after it name the check that failed, for example "the weather was fetched in
  other units than yours".
- **"Skipped":** the question or the chat didn't meet the cache rules, and the trace says **Bypassed** with the
  reason. A question outside these five earlier in the chat does this; choose **New chat**. A park, trip or
  memory question skips the cache with no "Skipped" line; its trace still says **Bypassed**.
- **"Unavailable; normal answer flow continues":** Qdrant didn't answer, and the trace says **Error**. The answer is
  still a correct, fresh one.
- **"No reusable answer" where you expected a match:** the saved entry expired, and is gone from
  [Weather cache](/weather-cache), or no saved question reached the cutoff (similarity search **Miss**, no score).
  Check that the earlier prompt's store said "Answer saved".
- **A similar match is likely, not guaranteed.** A miss falls back to a fresh answer, which is still correct.
- **After an entry expires,** the next ask uses Gemini and the weather tools again, though Open-Meteo's replies may
  still come from Nimbus's own provider cache.
