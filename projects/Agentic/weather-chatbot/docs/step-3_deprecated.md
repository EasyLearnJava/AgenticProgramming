# Step 3 · The Live Chat, Through REST · No Auth

**What this step built:** the chat answers for real. Your question goes to Gemini, which calls our four weather tools;
on this lane, `REST · no auth`, each tool calls Open-Meteo's API itself, over HTTPS, with no credentials. Every call
shows as a chip you can open, and a forecast gets a weather card.

## What you see

- **The first message** says what Nimbus does, with questions to try. If Vercel knows roughly where your network is,
  one more question names the nearby city; it's only ever offered, never used unless you pick it.
- **Ask a question,** and Send turns into **Stop** while the answer comes in. Each tool call appears as a chip above
  the answer: `…` while it runs, `✓` when it's done, `✗` if it failed, `■` if the answer stopped before it finished.
- **The answer** is Markdown: paragraphs, lists, bold. Images in it aren't shown (the browser would fetch them from
  wherever the model pointed), and its links open in a new tab, so the chat stays. **New chat** starts over.
- **Open a chip** to see the request exactly as it went out (On the wire), its input and its output. A done chip says
  its lane, the host it called, and how long it took, or "from the cache".
- **The weather card** under a forecast: the place, a row per day (condition, lowest and highest temperatures, the
  highest chance of rain), and when the data was fetched, in the place's own time.
- **The pin** puts your location into the question, rounded to about 1 km, after the browser asks you. You can edit
  the question before sending it.
- **The lane picker:** `REST · no auth` is the only live lane, so a chat starts there. The plan's default lane, `MCP ·
  no auth`, takes over in step 4, when it's live; the other lanes stay switched off until their step.
- **If something fails,** you get a plain sentence and Try again; a failed tool call says so on its chip. If an answer
  runs past its time budget, a note under it says it was cut short.

## How it works

### One question, step by step

1. **The page** (`components/chat-window.tsx`) sends your question with AI SDK's `useChat` to `POST /api/chat`, with
   the lane and your browser's locale (which picks metric or imperial units to start with).
2. **The route** (`app/api/chat/route.ts`) checks the request (`lib/chat/chat-request.ts`): at most 20 messages, each
   of yours at most 2,000 characters, the whole history at most 200,000 characters (it all goes to the model), only
   the parts the page sends, each earlier tool call's input valid for its tool, a live lane, a real language tag, and
   messages in AI SDK's shape. A request that breaks a rule gets `400` and a sentence saying which rule. The page
   sends only the recent messages, so a long chat keeps working.
3. **The model** (`lib/chat/model.ts`) is Gemini, `gemini-3.5-flash-lite`, with your `GOOGLE_API_KEY`. Without the
   key, the route answers `503`: "The assistant isn't set up on this deployment yet."
4. **The lane** (`lib/lanes/open-lane.ts` opens `lib/lanes/rest-no-auth.ts`) hands the model our four tools.
5. **One chat turn** (`lib/chat/run-chat.ts`) streams the answer with `streamText`: the system prompt, the tools, at
   most 5 steps, a cap on what the model writes, and the time budgets below.
6. **The model calls tools.** For the Paris question: `geocode_location("Paris")`, then `get_forecast(48.85, 2.35, 2
   days, hourly)`. Each tool calls Open-Meteo, and its result streams to the page as it finishes.
7. **The model writes the answer** from those results only, and the page shows it under the chips.

### The four tools, written once

| Tool | What it asks Open-Meteo | What the model gets back |
|---|---|---|
| `geocode_location` | `geocoding-api.open-meteo.com/v1/search`, in English | the places found (name, region, country, coordinates, time zone, population) and `isAmbiguous` |
| `get_current_weather` | `api.open-meteo.com/v1/forecast` with `current=` | temperature, feels like, wind, the condition in words, day or night, when it was observed |
| `get_forecast` | the same API, per day and, if asked, per hour (the first 3 days) | per day: condition, lowest and highest, the highest chance of rain, sunrise, sunset; per hour: temperature, rain, condition |
| `get_air_quality` | `air-quality-api.open-meteo.com/v1/air-quality` | PM2.5, PM10, the European and US AQI, when it was observed |

- Each tool is a plain object in `lib/weather/tools/`: a name, a description, an input schema (Zod), how it runs,
  and a one-line summary for its chip. `lib/weather/open-meteo-tools.ts` lists the four; step 4's MCP server will
  register the very same list.
- **Every request** sends `timezone=auto`, so times are the place's own, and coordinates rounded to 2 decimals
  (about 1 km). Imperial units are Open-Meteo's own conversion (`temperature_unit=fahrenheit`, and so on).
- **The weather codes** Open-Meteo returns (0 clear sky, 1 mainly clear, …) become words from one table
  (`lib/weather/wmo-codes.ts`), so the words never come from the model's memory.
- **What the model reads, and what the page shows.** A tool's result reaches the page with its request, its time and
  whether the cache answered (the chip). The model gets only the weather: the tool's `toModelOutput` strips the rest.

### The ambiguity rule

`lib/weather/ambiguity.ts` decides, in code, whether a name may mean more than one place: it sorts the places by
population (Open-Meteo sorts them by relevance), and calls the name ambiguous when the largest place in another region
has at least a third of the largest one's population, or when the largest one's population is unknown. The bot then
asks which place you mean, and fetches no weather.

| Name | Open-Meteo's answer on 29 October 2026 | Ambiguous? |
|---|---|---|
| Paris | Paris, France (2,138,551); then Paris, Texas (24,782) | no |
| Springfield | Missouri (170,188), Illinois (114,394), Massachusetts (154,341) | yes |
| Springfield, MA | five places, all in Massachusetts: a region after a comma narrows the search | no |
| Narnia | three places, none with a population | yes |
| Atlantis | Atlantis, Western Cape, South Africa (82,736): a real town | no |
| Hogwarts | no places at all | no (nothing to ask) |

### Time limits, retries and the cache

| What | Limit | What happens then |
|---|---|---|
| One try at Open-Meteo | 3 s | one more try after a short random wait; a `5xx` is retried the same way |
| Open-Meteo answers `429` | — | retried only if its `Retry-After` is under 1.5 s; else the tool fails, "The weather service is busy" |
| One tool call | 8 s | the tool fails, and its chip says so |
| The model's first chunk | 10 s | the answer stops, with a note that it was cut short |
| The whole answer | 50 s (the function stops at 60 s) | the same |

Open-Meteo's answers wait in Vercel's Runtime Cache, keyed by the request's URL: 30 days for geocoding, 10 minutes for
the weather now, 30 minutes for forecasts and air quality. A chip answered from the cache says so; its wire view shows
the request that fetched it.

### When something fails

Every failure becomes one of a few error classes (`lib/errors.ts`), each with its own plain sentence: the page never
shows Open-Meteo's, Gemini's or Vercel's own error text (an error response the chat didn't mark as its own becomes
"The chat couldn't be reached."). Each failure is also logged, as one JSON line in Vercel's logs (`lib/logger.ts`):
its class and our message, never your question. The fifth and last step of an answer can't call a tool, so an answer
never ends on tool calls without words. Step 5 adds the rest: request ids, the full logger, alerts.

Every problem met while building this step, and its fix, is in **Issues and fixes**, in the left menu.

## The checks this step added

- **Unit tests** (100 in all) on Open-Meteo's recorded answers from 29 October 2026 (`tests/fixtures/open-meteo/`):
  the requests, the renamed fields, the cache, the retries, every failure, each tool, the ambiguity rule, the WMO
  table, the request limits, the system prompt, the logger, the lane's logging, and the route's refusals.
- **A whole chat turn** (`tests/unit/chat/run-chat.test.ts`) with AI SDK's mock model in place of Gemini: both chips
  stream with their records, the answer follows, and the model's second call gets only the weather.
- **End-to-end tests** in a real browser answer the page's `/api/chat` with a recorded answer, so no model is called:
  the chips, the wire view, the weather card, a failure with Try again, Stop, the pin, the nearby city, axe, and a
  360-pixel screen.
- **The golden questions** (`tests/evals/golden.eval.ts`) ask a running deployment, so the real model answers: Tokyo
  now, the Paris umbrella question, Springfield (asks which), Hogwarts (can't find it), and a poem (declined).

```bash
EVAL_BASE_URL=https://weather-chatbot-hazel.vercel.app npm run evals
```

## Set up the key

The chat needs a Gemini API key, the same one the repo's other projects use.

- **On Vercel:** the project's **Settings → Environment Variables**, add `GOOGLE_API_KEY` (Production and Preview),
  then redeploy: a deployment keeps the settings it was built with.
- **On a laptop:** copy `.env.example` to `.env.local` in this folder and put the key after `GOOGLE_API_KEY=`.
  `.env.local` never goes into git.

## Files in this step

| File | What it does |
|---|---|
| `app/api/chat/route.ts` | The chat endpoint: checks, then streams |
| `app/api/nearby-city/route.ts`, `hooks/use-nearby-city.ts` | The nearby city, from Vercel's location headers, for one suggested question |
| `lib/chat/chat-request.ts`, `model.ts`, `system-prompt.ts`, `run-chat.ts` | The request's rules, the model, the system prompt, one chat turn |
| `lib/chat/lane-examples.ts` | The compare view's four requests (step 2's sample conversation is gone) |
| `lib/lanes/lane.ts`, `open-lane.ts`, `rest-no-auth.ts` | What a lane is, opening one, and `REST · no auth` |
| `lib/upstream/open-meteo.ts` | The calls to Open-Meteo: time limits, the retry, the cache, our names for its fields |
| `lib/weather/tools/*.ts`, `weather-tool.ts`, `open-meteo-tools.ts` | The four tools, their shape, and their list |
| `lib/weather/ambiguity.ts`, `wmo-codes.ts` | The ambiguity rule, the weather-code table |
| `lib/errors.ts`, `lib/logger.ts` | The error classes and their sentences; one JSON log line per failure |
| `components/answer-markdown.tsx` | An answer's Markdown, without images, with links in a new tab |
| `app/issues/page.tsx`, `docs/issues.md` | **Issues and fixes**: the problems met in each step, and their fixes |
| `lib/config.ts`, `.env.example` | The settings: now with `GOOGLE_API_KEY` and `CHAT_MODEL` |
| `components/chat-window.tsx`, `chat-welcome.tsx`, `chat-message.tsx`, `tool-chip.tsx`, `weather-card.tsx`, `chat-input.tsx` | The live chat |
| `tests/unit/**`, `tests/fixtures/open-meteo/`, `tests/stubs/open-meteo-stand-ins.ts` | The unit tests, Open-Meteo's recorded answers, and the stand-ins for the network and the cache |
| `tests/e2e/chat-page.spec.ts`, `tests/e2e/chat-stream.ts` | The browser tests, and the recorded answer they use |
| `tests/evals/golden.eval.ts`, `vitest.evals.config.ts` | The golden questions |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm install
npm test
npm run build
npm run e2e
npm run dev
```

Then open http://localhost:3000 and ask the Paris question (with your key in `.env.local`; without it, the page says
the chat isn't set up). Open the `get_forecast` chip: its request is the one in the wire view, and you can paste its
URL into a browser to see Open-Meteo's own answer.

**A note on cost and abuse:** until step 8 adds the bot check and the rate limit, anyone who finds the URL can use the
chat, and with it your Gemini quota. The limits above (20 messages, 200,000 characters in all, 5 steps, a cap on the
answer) bound each request, not how many requests come.

## What's next

**Step 4:** `MCP · no auth`. Our own MCP server at `/api/mcp` registers the same four tools, and the chat reaches them
through MCP instead: the same answer, through another door.
