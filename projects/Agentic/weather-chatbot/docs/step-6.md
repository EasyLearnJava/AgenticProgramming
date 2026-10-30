# Step 6 · REST · With Auth, Through Apify's Actor

**What this step built:** the third lane, `REST · with auth`. Its forecasts come from an Apify Actor, the Open-Meteo
Weather Forecast Actor, run through Apify's REST API with a token that stays on the server; finding the place is still
Open-Meteo's geocoding. When Apify can't answer, the lane asks `REST · no auth` for the same forecast, and the chip
says so.

## What you see

- **In the picker,** `REST · with auth` is live on a deployment that has Apify's token (`APIFY_TOKEN`), and says
  "needs an Apify token", switched off, on one that doesn't. The compare view says the same.
- **Its forecast chip** is the Actor's tool, under Apify's own name, `gochujang--open-meteo-weather-forecast`. Opened,
  it shows a `POST` to Apify with `authorization: Bearer <APIFY_TOKEN>`: the token is masked here and in the compare
  view, and never goes in the URL.
- **When Apify can't answer,** the chip gets a line of its own, in amber: "REST · with auth is unavailable: Apify
  didn't accept our token. Answered through REST · no auth instead. (ref b1a0d9e8)". Its lane then says
  `REST · no auth`, its wire view shows the Open-Meteo request that answered, and the answer and the weather card are
  as on that lane.
- **An hourly answer** through the Actor ("Will it rain this afternoon?") gets its chips and its answer, but no
  weather card: the Actor's hourly mode gives hours, and a card shows days.
- The two no-auth lanes look as before.

## How it works

### One call, the third way

The lane's code marks the six points every lane has (PLAN.md 4.3):

1. **Where:** `POST https://api.apify.com/v2/acts/gochujang~open-meteo-weather-forecast/run-sync-get-dataset-items`,
   which runs the Actor and answers with its dataset's items, in one request (`lib/upstream/apify.ts`).
2. **Auth:** `Authorization: Bearer` with `APIFY_TOKEN`. Only the request's header holds the token: never the URL,
   which logs and the wire view would keep, and never the page.
3. **Tools:** `geocode_location`, Open-Meteo's, as on `REST · no auth` (the Actor can't find places), and the Actor's
   tool, with the Actor's own input: one location (a name and coordinates), `forecastDays` from 1 to 16, and `mode`,
   `daily` or `hourly`. Ours adds `units`: the Actor has no such option, so the lane converts °C to °F itself and
   never sends it. The system prompt names the lane's own tools; this lane has none for the weather now or the air,
   so the model says so and gives today's forecast.
4. **The call:** the Actor's input as the body, and three limits in the URL: `build=1.0.9`, so a new build of the
   Actor can't change its answer under us; `timeout=18`, so Apify stops a run after 18 s; and
   `maxTotalChargeUsd=0.01`, so a run can't cost more than a cent (one costs about half a cent: $0.003 to start, and
   $0.002 a forecast).
5. **The result:** the Actor's items, read into the same `Forecast` that `get_forecast` gives
   (`lib/weather/actor-items.ts`), so the model, the chip and the weather card see one shape on every lane.
6. **Clean-up:** none: a REST lane holds no connection. The Actor's tool gets 28 s instead of a tool's usual 8: 20 s
   for the run (Apify stops it at 18) and the trip, then 8 s for the fallback.

### The Actor's answer, as it really comes

The Actor's page doesn't say what it returns. Its README speaks of one record per location, with "time-series
arrays" for the daily and hourly forecasts, and this step's first version read that. Its first run on the live site
showed otherwise (bug story 12): one item per day in daily mode, and one per hour in hourly mode, each carrying its
place (`location`, `latitude`, `longitude`, `timezone`) and the Actor's own field names, in °C:

| Mode | One item is | The fields we read |
|---|---|---|
| `daily` | a day | `date`, `weather_code`, `temp_max_c`, `temp_min_c`, `precipitation_probability_pct`, `sunrise`, `sunset` |
| `hourly` | an hour, from the place's midnight | `datetime`, `weather_code`, `temperature_c`, `precipitation_probability_pct` |

`actor-items.ts` checks that shape with Zod; that every item is for the place asked, at the coordinates the lane sent,
which the Actor echoes; and that the days asked are all there, one after another. Anything else is a `ContractError`
that names the field, never its value, and the lane falls back rather than guess. Hourly mode gives no day's summary, so
a forecast of hours has no days: its chip sums up the hours ("24 hours · 20 to 27 °C · rain up to 17%"), it gets no
weather card, and the tool takes hourly mode for at most 3 days, as `get_forecast` gives hours. The tests read the
Actor's real answers for Dallas, saved whole in `tests/fixtures/apify/`.

### Falling back

When the Actor's call fails, the tool doesn't: it logs the failure once, as `lane.fallback`, at its class's level,
with the lane it left, the lane it's using and Apify's own words. Then it asks `REST · no auth`'s `get_forecast` for
the same place, days, hours and units. The result says it fell back: the lane it came from, and the sentence its chip
shows. The model reads only the forecast, in this turn and in later ones, whichever lane the chat has moved to (bug
story 11).

| What happened | Class | The chip says | Level |
|---|---|---|---|
| Apify doesn't accept the token: `401` (its body says `user-or-token-not-found`), or `403` | `AuthError` | "Apify didn't accept our token" | error, so with the ref |
| Apify asks for payment: `402` | `BudgetExceededError` | "Apify's credit for this month is used up" | warn |
| The run took too long: Apify's `408`, or past its 20 s | `UpstreamTimeoutError` | "Apify took too long" | warn |
| Apify is busy: `429` | `UpstreamRateLimitedError` | "Apify is busy" | warn |
| Apify fails, or can't be reached: a `5xx`, or no answer | `UpstreamUnavailableError` | "Apify can't be reached" | warn |
| Apify refuses the run (another `4xx`), or answers in a shape we don't read | `ContractError` | "Apify answered in a way we didn't expect" | error, so with the ref |

The fallback gets the tool's last 8 s, and starts only with at least 12 s of the answer's 50 left, so the answer can
still be written; with less, the call fails with its own sentence (PLAN.md 9.3). Stop, or the answer's budget running
out, ends the run and the fallback alike, and then nothing falls back: the answer is ending (bug story 10). A run is
never retried or cached: each one costs money, and the fallback answers anyway.

**The `402`:** without a token, Apify answers `402` and asks for payment in USDC (x402; PLAN.md section 3, row 13).
This lane never runs without one, so a `402` here means our token can't pay: the month's credit is used up. Apify's
docs don't say which status a used-up credit gets, so this is our reading until it happens; the `lane.fallback` line
keeps Apify's own words to check it by (issues log, entry 72).

### What Apify sees, and what the logs keep

Apify gets the place's name, its coordinates (rounded to about 1 km), the days and the mode: never your question,
and never who asked. The token is a Secret in Vercel's settings, which can't be read back once saved; the logs never
hold it (pino redacts `authorization` and `token` fields), and the wire view masks it. Apify's error messages can
quote the input, so a line keeps only an error's type, and its message too only for an account's problem (`401`,
`402`, `403`).

`REST · with auth` adds two lines to a question's: `upstream.http` for the run, with `upstream: "apify"`, its status,
time and number of items; and, when it falls back, `lane.fallback`. The `tool.call` line of a call that fell back
says `fallbackFrom: "rest-auth"`.

### The token, at build time

The chat page is static: Next.js builds it once per deployment, so whether `APIFY_TOKEN` is set is read when the
deployment is built. Vercel applies a changed variable only to new deployments anyway, the functions included: set the
token, then redeploy (issues log, entry 73). A request for the lane where the token isn't set, from an old tab or a
script, is refused before anything opens, as a broken rule: "That message can't be sent: that lane needs an Apify
token, which this deployment doesn't have."

## Not in this step

- **The token check that runs nothing** (`GET /v2/users/me`, PLAN.md section 3, row 14) comes with the health check
  (step 9), the first code that needs it.
- **Step 0's spike,** a run by hand before this step, never happened: the first run on the live site answers its
  questions about the REST door (what the Actor returns, how long a run takes, what it charges, its units); the MCP
  door's wait for step 7.
- **Preview deployments** don't have the token: it's set for Production only, like the Gemini key. So the plan's
  check, on preview, runs on the live site instead.
- **A limit on what the lane spends.** Each forecast costs about half a cent of Apify's credit, $5 a month on the free
  plan (about 1,000 forecasts), and anyone with the URL can spend it. Step 8's rate limit caps requests; until then, a
  used-up credit makes the lane fall back, nothing worse, as long as the Apify account stays on the free plan, where a
  used-up credit stops runs until the next month.

## The checks this step added

- **The Apify client** (`tests/unit/upstream/apify.test.ts`): the request (the token in the header, masked in the
  record, never in the URL; the limits in the URL); each status as our class, with Apify's real answer to a fake
  token; no answer, too slow, Stop (while the answer is still arriving, too); its log line, which never holds the
  token.
- **The Actor's items** (`tests/unit/weather/actor-items.test.ts`): its real answers for Dallas, daily and hourly
  (`tests/fixtures/apify/`), as our days and hours; °F when asked; another shape, another place, or a missing,
  doubled or skipped day refused, naming the field.
- **The Actor tool** (`tests/unit/weather/tools/open-meteo-actor.test.ts`): its input (one place; hourly for at most 3
  days), and its summary of days, or of hours.
- **The lane** (`tests/unit/lanes/rest-auth.test.ts`): its two tools and the Actor's 20 s; a forecast through the
  Actor; each way it falls back (a rejected token, used-up credit, a shape we don't read, too slow), with the chip's
  sentence and the one line; Stop, during the run and during the fallback; the answer's own budget firing during the
  run, and under 12 s of it left: no fallback.
- **What the model reads** (`tests/unit/chat/run-chat.test.ts`): after the chat moves to `REST · with auth`, an
  earlier `get_forecast` result still reaches the model as the weather alone.
- **The error map, played out** (`tests/unit/chat/error-map.test.ts`): `AuthError` and `BudgetExceededError` through
  a whole turn on `REST · with auth`, the two classes step 5 left for this step.
- **The smaller pieces:** which lanes a deployment runs (`open-lane.test.ts`), the token's setting
  (`config.test.ts`), the two classes (`errors.test.ts`), °F (`utils.test.ts`), the rules for each lane's tools
  (`system-prompt.test.ts`), the Actor tool's calls in a chat's history and a request for the lane without the token
  (`chat-request.test.ts`), and the compare view's request (`lane-examples.test.ts`).
- **In the browser** (`tests/e2e/chat-page.spec.ts`): the picker and the compare view agree on `REST · with auth`,
  with the token or without; a recorded fallback shows on its chip, with the weather card, and passes axe.

## Files in this step

| File | What it does |
|---|---|
| `lib/upstream/apify.ts` | The Actor's run: the request, the token, the limits, each status as our class, `upstream.http` |
| `lib/weather/tools/open-meteo-actor.ts` | The Actor's tool, under Apify's name, with the Actor's input and our units |
| `lib/weather/actor-items.ts` | The Actor's items as our `Forecast`, in the units asked for; any other shape a `ContractError` |
| `lib/lanes/rest-auth.ts` | `REST · with auth`: its two tools, the Actor's budget, the fallback to `REST · no auth` |
| `lib/lanes/lane.ts`, `lib/lanes/open-lane.ts`, `lib/lanes/rest-no-auth.ts`, `lib/lanes/mcp-no-auth.ts` | The fallback's sentence and `toModelWeather()`, what the model reads of any result; which lanes a deployment runs; `REST · no auth`'s tool runner, now shared |
| `lib/chat/run-chat.ts`, `lib/chat/system-prompt.ts`, `lib/chat/chat-request.ts`, `lib/chat/lane-examples.ts` | A tool's own budget, and the history read with every lane's tools; the rules for the lane's tools; every lane's tools for a chat's history, and a lane this deployment runs; the compare view's request |
| `app/api/chat/route.ts` | The lanes this deployment runs, for the request's rules |
| `lib/errors.ts`, `lib/config.ts`, `lib/constants.ts`, `lib/types.ts`, `lib/utils.ts` | `AuthError` and `BudgetExceededError`; `APIFY_TOKEN`; the Actor's address and limits; the fallback's types; `celsiusToFahrenheit` |
| `app/page.tsx`, `components/*.tsx`, `app/globals.css` | The lanes this deployment runs, in the picker and the compare view; the fallback on the chip; the Actor's daily forecast in the weather card |
| `tests/stubs/apify-stand-ins.ts`, `tests/fixtures/apify/` | A fetch that answers as Apify does; Apify's real `401`, and the Actor's real answers for Dallas, daily and hourly |

## Check it yourself

From `projects/Agentic/weather-chatbot`:

```bash
npm test
npm run build
npm run e2e
```

To run the lane, make a token in an Apify account used only for this bot, since the token opens the whole account:
in Apify Console, **Settings → API & Integrations**. Add it in Vercel as `APIFY_TOKEN` (**Settings → Environment
Variables**, type **Secret**), then redeploy. On a laptop, put it after `APIFY_TOKEN=` in `.env.local`. Then ask on
`REST · with auth` about a city's weather in the coming days, and open the forecast chip: its lane says
`REST · with auth`, and its wire view shows the `POST` to Apify.

## Checked on the live site

On 29 October 2026, once this step was live as `7ad3904` (its CI run had passed):

- **The token reached the build.** The picker showed `REST · with auth` as live, so the deployment was built with
  `APIFY_TOKEN` set (a Secret, for Production only).
- **The Actor ran, and its answer wasn't the shape we read.** "What's the weather in Dallas, Texas for the next 3
  days?": Apify answered `201` with 3 items in 3,498 ms, the run itself taking 3 s, 1.2 s of it pulling the Actor's
  container. Apify Console showed our limits on the run (build 1.0.9, an 18-second timeout, $0.01 at most) and its
  cost: $0.005. The lane refused the items ("The Actor gave 3 items for one location."), fell back, and said so on the
  chip, with the ref `96b42d86`; the answer, from `REST · no auth`, was right. Bug story 12 tells the rest.
- **Hourly mode.** Two hourly runs gave 24 and 48 items, one an hour, and no day's summary, for $0.005 each: the
  price is per place, whatever the days or mode, so the $0.01 cap can't cut a forecast short.
- **After the fix, through the Actor.** Once `a6365c5` was live (its CI run had passed), the same Dallas question ran
  the Actor with no fallback: its chip said `REST · with auth`, its wire view showed the `POST` to Apify with
  `authorization: Bearer <APIFY_TOKEN>`, and the call took 3,642 ms. The answer gave Thursday's high of 80 °F and low
  of 68 °F. An hourly question got its 48 hours in 4,498 ms, also with no fallback.
- **One wrong answer, from the model.** Asked about "tomorrow afternoon" at 21:50 in Dallas, already 30 October in UTC,
  the model evidently took tomorrow to be 31 October: it said the hours didn't reach that afternoon; they did.
  `REST · no auth`'s answer had made the same slip earlier that evening, so it isn't this lane's. It's fixed since:
  issues log, entry 87, and bug story 13.
- **No step went backwards.** The browser tests passed against the live site, 48 of 48, with the token set: the
  picker and the compare view showed `REST · with auth` as live.

## What's next

**Step 7:** `MCP · with auth`: Apify's MCP server with the same token, the same Actor and the same reading of its
items, and the fallback to `MCP · no auth`.
