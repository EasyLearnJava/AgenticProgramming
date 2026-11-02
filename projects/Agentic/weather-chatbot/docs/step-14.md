# Step 14 · Observability: Activity, Performance, Evaluations, Health, and the Menu in Groups

Step 14 reads the app's own lines back. Since step 12, every line the app logs goes to Axiom; now four pages show
them to anyone who opens the site, as words, numbers and bars: Activity, the latest lines; Performance, how long
answers and tools take; Evaluations, the golden questions' last run and how live answers end; and Health, the checks
now and how often they passed, with our MCP server's address. Each page asks Axiom with a second token, one that can
only query; each query names the fields it reads, so nothing private can reach a page, and the lines never held
anything private anyway (step 11). The menu's links are grouped too, the TypeScript app's pages folded away.

**In one line:** a token that can only query → each page's queries, once a minute on each copy → only the fields
they name → words, numbers and meters → kept a minute by the CDN → the menu in groups.

## What you'll build

- `nimbus/axiom_query.py`: one APL query to Axiom's query door, its table back as rows.
- `nimbus/observability.py` and four templates: Activity, Performance, Evaluations and Health.
- `nimbus/goldens.py`: the golden questions, shared by the evals and the Evaluations page, and `--save`, which keeps a
  run in `evals/last-run.json`.
- The menu in groups: App, Observability, Learn, Project, Links, and Deprecated, folded.

## What you'll learn

- How to read your own logs back onto a public page without showing anything private.
- How to keep a page anyone can open from running up a log service's bill.
- How to draw bars under a Content Security Policy that refuses inline styles.

## Before you start

- Step 13's project; nothing new to install.
- In Axiom and Vercel: a query token, `AXIOM_QUERY_TOKEN` ([Waiting on you](waiting-on-you.md), part 6). Without it,
  each page says it can't read Axiom yet, and Health still shows the checks now.

## The design

![Step 14 · Observability](images/step-14-design.svg)

| Decision | Why |
|---|---|
| A second Axiom token, an advanced one that can only query the one dataset, with an expiry and Axiom's cost caps | The ingest token can't read, and this one can't write; a leak of either does less, and the caps hold a bill |
| Each query names the fields it reads (`project`), never `*` | A field a later step adds can't reach a public page by accident |
| A field not every line has is read through `column_ifexists`, with a default | Axiom refuses a query that names a field it has never seen, as a young dataset hasn't (issue 85) |
| Activity's filters chosen by name from our own list; any other is a 404 before anything is asked | Nothing a visitor types goes into a query, and a made-up filter costs nothing |
| Each query once a minute on each copy, a failed one too; the CDN keeps a page that answered a minute more | A page anyone can open, opened often, still asks Axiom each of its 11 queries at most once a minute on each copy |
| A page Axiom couldn't answer is never kept, and shows our sentence, never Axiom's | The next visit asks again; Axiom's words could name the token or the query |
| A refused query is an error once on each copy, then a warning, until it answers; a refused token, once for every query | Sentry hears of it, as for the health check (issue 74), without using up its quota (issue 84) |
| Rendered on the server, no script | The token stays on the server, the page works without JavaScript, and the CDN keeps one page for every visitor |
| A bar is a `<meter>`, its words beside it | The policy refuses an inline style, which a bar's width would need; a meter is drawn by the browser and read by screen readers |
| The golden questions' last run kept in the repository | The evals run from your computer; the page reads what they kept, and asking them again costs Gemini's quota |
| No link to your Axiom, Sentry, LangSmith or Vercel dashboards | The site is public; their addresses name your accounts |

## Files

| File | What it does |
|---|---|
| `nimbus/axiom_query.py` | One APL query, POSTed to Axiom's query door with the query token; the first table, as rows; each failure by its code |
| `nimbus/observability.py` | The queries, each once a minute on each copy; the rows in words and numbers; the four pages |
| `templates/activity.html`, `performance.html`, `evaluations.html`, `health.html`, `observability_parts.html` | The pages, and what they share: the notice, the numbers, a breakdown of meters |
| `nimbus/goldens.py` | The golden questions and the last run kept, read and checked (moved from `tools/evals.py`, which Vercel leaves out) |
| `nimbus/health.py` | Each line a check writes names its check, so Performance leaves the health check's own fetches out |
| `tools/evals.py` | `--save`: the run kept in `evals/last-run.json` |
| `nimbus/pages.py`, `templates/base.html` | The menu in groups; the deprecated group folded unless it holds the page |
| `nimbus/config.py`, `nimbus/constants.py`, `nimbus/errors.py`, `nimbus/app.py`, `.env.example` | The query token, the limits, the sentences, the wiring |
| `public/static/app.css` | The groups, the numbers, the meters, the lines |
| `tests/unit/test_axiom_query.py`, `test_observability.py`, and the pages', evals' and fakes' changes | Axiom played back: each page, each failure, the minute, the CDN, the menu |
| `tests/e2e/conftest.py`, `tests/e2e/test_site.py` | The pages in a browser, with Axiom played back; the groups, the fold, the filters |
| `tools/mutation_check.py` | 21 more rules |

## How it works

### Asking Axiom: `nimbus/axiom_query.py`

1. **The query and its time range in the body, the token in a header** (①): `{"apl", "startTime", "endTime"}` to
   `https://us-east-1.aws.edge.axiom.co/v1/query/_apl?format=tabular`, the same US edge the lines go to (step 12).
   Axiom's API reference for its edge query says its older `/v1/datasets/_apl` path isn't served on an edge domain,
   and Axiom's own Python client sends only API tokens there, never a personal one.
2. **One POST within 5 s** (②): past it, `axiom_timeout`; no answer at all, `axiom_unreachable`.
3. **Its status, then its table** (③): 401 or 403 is `axiom_refused`, 429 `axiom_limited` (Axiom's own cost cap,
   say), another 4xx `axiom_bad_query`, a 5xx `axiom_unreachable`. A 200's first table, never the one of totals Axiom
   may add, named `_totals`, is read as rows: each field's name, and its column, one value a row. No table, or no
   columns, is no rows; columns that don't match the fields, or anything else, `axiom_unreadable`. Each is an
   `ObservabilityError` by its code, never with Axiom's words.

### The queries: `nimbus/observability.py` ①

Each runs over the dataset, `['weather-chatbot']`, from settings checked when the app starts. `_time`, `event`,
`level`, `status` and `ms` are on every request's own line, `http.request`, so the dataset has them once the app has
answered once; any other field comes from rarer lines, and Axiom refuses a query naming a field it has never seen,
so those are read as `column_ifexists('lane', '')`, written `lane′` below. `status` holds a number on some lines
(`http.request`'s 200) and words on others, so it's compared as `tostring(status)`:

| Page | Query |
|---|---|
| Activity | `where <the filter> \| sort by _time desc \| take 50 \| project _time, event, level, lane′, tool′, status, ms, errorClass′, code′, toolCalls′, tokensIn′, tokensOut′, fromLane′, toLane′` |
| Performance | `where event == "chat.done" \| summarize answers = count(), p50 = percentile(ms, 50), p95 = ..., p99 = ..., avgToolCalls = avg(toolCalls′), avgTokensIn = ..., avgTokensOut = ...` |
| Performance, Evaluations | `where event in (<the chat's five>) \| summarize lines = count() by event, lane′` |
| Performance | `where event == "tool.call" \| summarize calls = count(), failed = countif(tostring(status) == "failed"), totalMs = sum(ms), slowestMs = max(ms) by tool′, lane′` |
| Performance | `where event in ("upstream.cache", "upstream.http") and upstream′ == "open-meteo" and isempty(check′) \| summarize lines = count() by event, status = tostring(status)` |
| Evaluations | `where event in ("chat.rejected", "chat.failed", "lane.fallback") \| summarize lines = count() by event, code′, errorClass′` |
| Health | `where event == "health.done" \| extend day = bin(_time, 1d) \| summarize runs = count(), down = countif(tostring(status) == "down") by day \| sort by day desc` |

Activity's filters (all, questions, tools, health, errors) are where clauses of our own, picked by name; an address
naming any other is a 404 before anything is asked. "All" leaves the health checks to their own filter: every
page's dots and every uptime ping add one, and would bury the questions. A tool's time is added up by tool and by
lane from the same rows: a sum and a count add up exactly, where an average or a percentile wouldn't. Open-Meteo's
answers leave out the health check's own geocoding, which skips the cache on purpose: each line a check writes
carries its `check` (`health.py`).

### Once a minute on each copy ②

`ask()` keeps each query's run, keyed by its APL, on the app's state: a request within a minute of a run's start gets
its rows, waited for if it's still going, shielded, so a visitor who leaves doesn't stop it for the rest; a failed run
answers its minute too. `run_query()` asks over the last 7 days and writes one `observability.query` line: the query's
name, how it went, its time, its rows; a failure by its class and code, at error when Axiom refused the token or the
query and that's new on this copy, which reaches Sentry; else a warning, until the query answers. A refused token
is one fault, whichever query met it: an error once on each copy, not once for each of the 11 (issue 91).
`ask_axiom()` runs a page's queries at once; without the token or the dataset, none, and the page says Axiom isn't
connected; if one fails, the page shows our sentence instead of any of them.

### The rows, read ③ to ⑤

A field is read as a number or as words, whatever Axiom sent: a missing one is 0, or empty. A time is milliseconds
under a second, else seconds to a tenth. **Activity** turns each line into words: "Answered in 5.8 s · 2 tool calls ·
5,150 tokens in, 96 out", "get_forecast on REST · no auth in 412 ms", "Fell back REST · with auth to REST · no auth:
AuthError"; an event it doesn't show is left out; the lines are grouped by their day in UTC. **Performance** adds up
each tool's and each lane's calls; **Evaluations**, how answers ended and why; only the cache's hits count as from
the cache, never a value it couldn't read.

### The pages ⑥

Each is rendered on the server inside the shell. `respond()` lets Vercel's CDN keep a page a minute
(`public, max-age=0, s-maxage=60`, as `/api/health`) when everything on it answered, else `no-store`. **Health** runs
the same report `/api/health` gives, a run per address a minute (step 12), beside its history, and is kept only when
both answered and every lane that's on works; its days are the last 7, though 7 days before now reach into an
eighth; and it gives our MCP server's production address, which names no deployment. **Evaluations** reads the
golden questions and `evals/last-run.json`, and names the build that answered, never the address asked, which could
name a preview and its team; without a run kept, or with one that can't be read, it says how to keep one.

### The golden questions' last run: `tools/evals.py --save`

The golden questions' models moved to `nimbus/goldens.py`: the page needs them, and Vercel leaves `tools/` out of the
function. With `--save`, the run is kept in `evals/last-run.json`: the build that answered, when, and each
question's result, never the address asked, which could name a preview and its team; with LF line endings. Commit it,
and the page shows it once deployed.

### The menu in groups

`MENU_GROUPS` in `pages.py` lists each group and its links; the pages every step adds to come from the docs' registry,
by their slugs, and a test checks each is in one group. Each group's heading labels its list for screen readers. The
deprecated group is a `<details>`, open only when it holds the page. A link that leaves the site, the source on
GitHub, says so to a screen reader and is never marked current. Health's MCP section is the menu's "MCP server".

## Run it

On a computer with no query token (`uv run uvicorn main:app --no-access-log`, whose start line says
`"axiomQuery": false`), each page says so, and isn't kept; a filter we don't have is a 404:

```text
$ curl -s -o /dev/null -w "%{http_code} %header{cache-control}\n" http://127.0.0.1:8000/performance
200 no-store
$ curl -s http://127.0.0.1:8000/performance | grep -o "read Axiom yet[^<]*"
read Axiom yet: it needs a token that can query its dataset. The token's steps are on
$ curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/activity?show=everything"
404
```

The golden questions, asked of the live site and kept for the Evaluations page:

```text
$ uv run python -m tools.evals https://weather-chatbot-hazel.vercel.app --save
https://weather-chatbot-hazel.vercel.app, build ac9f985:
pass  rain-tomorrow: geocode_location, get_forecast
pass  weather-now: geocode_location, get_current_weather
pass  air-quality: geocode_location, get_air_quality
pass  ambiguous-place: geocode_location
pass  no-such-place: geocode_location
pass  too-far-ahead: -
pass  coordinates: get_current_weather
pass  metric-for-a-british-browser: geocode_location, get_forecast
pass  imperial-for-an-american-browser: geocode_location, get_forecast
pass  off-topic: -
pass  change-the-rules: -
pass  reveal-the-rules: -
FAIL  storm-safety: -
      called [], not ['get_forecast'] in that order
      doesn't say /National Hurricane Center|weather service|local (?:officials|authorities|emergency)/
12 of 13 passed
kept in evals/last-run.json
```

The storm question, asked once more, passed: Gemini called `geocode_location` and `get_forecast`, and pointed to the
National Hurricane Center (issue 92). The run kept is the one above, its miss and all: a run is kept as it went.

## Test it

```text
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
117 files already formatted
$ uv run mypy
Success: no issues found in 78 source files
$ uv run pytest
690 passed in 11.13s
$ uv run pytest tests/e2e --browser-channel msedge
205 passed in 143.87s (0:02:23)
$ uv run python tools/mutation_check.py
...
caught: Activity reads only the fields it names
caught: a filter we don't have is a 404
caught: the pages look back 7 days
caught: a query runs once a minute on each copy
caught: a page Axiom couldn't answer is never kept
caught: a refused token is an error once on each copy
caught: without the query token, nothing is asked
caught: only the cache's hits count as from the cache
caught: a 403 from Axiom is a refused token
caught: a table whose columns don't match its fields can't be read
caught: the deprecated group is folded unless it holds the page
caught: a link that leaves the site says so
caught: a query that answered is new again when it fails
caught: a Health page with a lane down is never kept
caught: Activity's all leaves out the health checks
caught: a field not every line has is read with its default
caught: the health check's own fetches are left out of the cache's share
caught: a run kept that can't be read is as none kept
caught: each line a check writes names its check
caught: a refused token reaches Sentry once, whichever query meets it
caught: never Axiom's table of totals
205 of 205 caught
```

Axiom played back, its answers in its tabular format: a query posted to the edge with its token and its time range;
the first table's rows, never the totals; each status Axiom may answer with, an Axiom out of reach or past its 5 s,
and an answer that isn't JSON, each by its code, never with Axiom's words. Each page without the query token, and
with it: Activity's lines in words, by day, never a field its query doesn't name, each filter's where clause written
out; Performance's numbers added up; Evaluations' golden questions, a run kept and one that can't be read; Health's
checks now, its days, our MCP server, and a lane down never kept. Each query once a minute on each copy; a refused
token or query at error once, then a warning; the menu's groups and its fold; and `--save`. In the browser, every
page, the new ones among them, with axe and at a phone's width, Axiom played back; the groups and the fold; a filter,
and the MCP server's section from the menu. The mutation check breaks 21 more rules (its first 184 lines are left
out above).

## Deploy it

The push, ac9f985, was live on Vercel within about 30 s of being pushed, and CI's checks passed. Checked on the live
site, https://weather-chatbot-hazel.vercel.app, on 2 November 2026, after warming it up:

- `/api/health` named the build, `ac9f985`, every lane working.
- Activity, its errors filter, Performance, Evaluations and Health each answered `200` in about 0.15 s, with
  `no-store`, and said "This deployment can't read Axiom yet": the query token wasn't set yet
  ([Waiting on you](waiting-on-you.md), part 6). `/activity?show=everything` answered `404`.
- Health said "Now: working", with our MCP server at `https://weather-chatbot-hazel.vercel.app/api/mcp`.
- The menu had its six groups, Deprecated folded, and the source's link marked as leaving the site; this chapter
  opened with its own title.
- The golden questions, under Run it: 12 of 13, kept in `evals/last-run.json`.

Then, on 2 November 2026 at 18:38 UTC, with `AXIOM_QUERY_TOKEN` set and production redeployed (still `2c8fbce`):

- Activity and its four filters, Performance, Evaluations and Health each answered `200`, with neither "can't read
  Axiom yet" nor "Axiom didn't answer", and showed rows: all 11 queries ran against the live dataset (issue 85).
  The name of Axiom's table of totals is still unseen: a page reads the first table that isn't it, and each showed
  its query's own rows.
- Separate queries agree: Performance's 95 answers (`ANSWERS`) are Evaluations' 95 answered (`ENDINGS`), and
  Evaluations' 13 failed are its 12 `AnswerTimeoutError` and 1 `UpstreamTimeoutError` (`REASONS`), the same 13 as
  Activity's errors filter (issue 93).
- The last 7 days still hold the TypeScript app's lines of 30 October, until 7 November: Health's history counts
  them (issue 95).

## Things to take care of, and pitfalls

- **Read back only what you'd log in public:** a page that shows lines is as private as the lines; name each field a
  query reads.
- **A page anyone can open is a query anyone can run:** keep each query's answer a while, let the CDN keep the page,
  and set the log service's own caps.
- **Never put what a visitor typed into a query,** a filter's name included: pick from your own list.
- **A schemaless store still refuses a field it has never seen:** read a field not every line has with a default.
- **Keep each failure by what failed:** one shared set, emptied by any success, makes an old failure new every time
  (issue 84).
- **A tool's code can't import from a folder the platform leaves out:** what both need goes in the app (issue 81).
- **Under a strict policy, a bar can't take its width from a style attribute:** use a `<meter>`, or a class.
- **Muted text on a tinted background can fall below 4.5:1:** axe finds it; give code in muted words the body's
  colour (issue 82).

## Issues we hit

81. The Evaluations page needed the golden questions, whose models lived in `tools/evals.py`, which Vercel leaves out
    of the function: they moved to `nimbus/goldens.py`.
82. axe found the evals command, in code inside muted words, at 4.39:1 contrast on its tinted background: code there
    keeps the body's colour.
83. The test of `--save` ran the evals twice, each run opening the app's lifespan: the MCP server's session manager
    runs once per instance. Both runs share one lifespan.
84. Both reviewers: one set of failures for every query, emptied when any answered, so a query failing beside others
    that answered was an error every minute, Sentry's quota spent. Each query's failure is kept by its name.
85. Both reviewers: a query naming a field the dataset has never had is one Axiom refuses, as a young dataset's would
    be. Every field not on every request's line is read with a default; `status`, a number on some lines, as words.
86. Reviewer A: the health check's own geocoding counted as fetched, so the cache's share looked near nothing. Each
    line a check writes names its check, and the count leaves those out.
87. Both reviewers: Activity's "All" would have been mostly health checks. They have their own filter.
88. Reviewer B: an unreadable `last-run.json` would have been a 500 on a public page. It's read as none kept, and
    said.
89. The reviewers: Evaluations printed the address the evals asked, and Health's MCP address could be a
    deployment's own: either could name a preview and its team. Neither does now, and the run kept has no address.
90. The reviewers: three tests couldn't fail as their names said, and three rules had none; each has a test that
    fails without it, and the mutation check 8 more rules.
91. The reviewers, again: with each query's failure kept by its name, a refused token reached Sentry once for each of
    the 11 queries on each copy. A refused token is one fault, kept by its code.
92. On the live site, the storm question answered once without a forecast and without the weather service, and
    passed when asked again: Gemini varies. The run is kept as it went. After the step it missed once more in 8 asks,
    naming a "National Hurricane Service", and rule 9 was made firmer: it names its tools and who warns, by their real
    names ([Issues and fixes](issues.md), 92).

Each is told in full, with how it was found and how it's checked, in [Issues and fixes](issues.md).

## Interview questions

**1. Why give a dashboard its own token, and what should it be allowed to do?**
Only what it does: query the one dataset, with an expiry and the service's cost caps. The token that writes logs can't
read them, and this one can't write; a leak of either does less.

**2. How do you keep a public page of your logs from showing private data?**
Log nothing private to begin with; then name each field a query reads, never all of them, and test that a field the
query didn't name never reaches the page.

**3. How do you stop a public dashboard from running up your log service's bill?**
Ask each query at most once a minute on each copy, a failure too; let the CDN keep the page; turn a made-up filter
away before asking; and set the service's own cost caps on the token.

**4. How do you draw a bar chart under a Content Security Policy with no inline styles?**
With `<meter>` elements, which the browser draws from their value and screen readers announce, their words beside
them; or a class for each step of width.

**5. Why render the pages on the server rather than query from the browser?**
The token stays on the server; the page needs no script; and one rendering, kept by the CDN, serves every visitor.

## Things to try

- Open Activity's Errors filter, then `/activity?show=anything`: a 404, and nothing asked of Axiom.
- Run the evals with `--save` against your computer, and open Evaluations; then `git restore evals/last-run.json`,
  so the repository keeps the live site's run.
- Add a query of your own to Performance, naming only the fields it shows, and a test that feeds it a field it
  doesn't name.

## What's next

Step 14 adds what the rebuild left for later; what could come next is on [To do](todo.md), and what's yours to set
is on [Waiting on you](waiting-on-you.md).
