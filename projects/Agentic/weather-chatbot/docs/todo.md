# To Do

What's still open, and why: first what waits on you, then BotID, then the rest of the plan. Each item says what it
needs and what it's for. Steps 1 to 7 are done and checked on the live site; step 8 is partly done, and step 9 has
begun.

## Waiting on you

| What | Why it's needed | Where |
|---|---|---|
| The two firewall rules: a bypass, then a rate limit of 20 requests a minute on `/api/*` | The rate limit caps abuse, and matters more while BotID is off; the bypass lets the chat's own calls to `/api/mcp` through, and later our evals past BotID | README, "Deploy it on Vercel", step 7 |
| The Ignored Build Step, in Vercel's project settings | Without it, every push to the repository rebuilds the app, even when nothing in its folder changed | README, "Deploy it on Vercel", step 4 |
| `GOOGLE_API_KEY` and `APIFY_TOKEN` for Preview deployments | Previews can't chat without them; today they're set for Production only. PLAN.md 9.4 splits the secrets between Production and Preview: a separate Apify token, or account, for Preview keeps previews from spending production's credit | Vercel, Settings, Environment Variables |
| The paid model path, before the URL is public | Gemini's free tier may use prompts to improve Google's products, and serving users in the EEA, Switzerland or the UK needs the paid service | PLAN.md, decision 3 (step 11) |

Done on 30 October: Axiom's dataset and token, and Sentry's project, DSN and token, set in Vercel for step 9.

## BotID, switched off

Step 8 put Vercel's BotID in front of the chat, and on the live site it refused every message we sent, for about 25
minutes, from one Chrome profile in two tabs: one our tools drove, one yours. It has been off since `810a981`; the chat
has no bot check meanwhile (bug story 17, entry 111).

**What's known:**

- **The page side worked:** BotID's script loaded from our own address, and the page's requests went through BotID's
  hook, so each message carried BotID's answer.
- **The answer reached the server:** BotID logs a warning when a request comes without one, and it did so only for a
  script we ran, not for the two tabs' messages. So Vercel's check read their answers and still called them bots.
- **Ruled out:** our security headers (Vercel serves BotID's paths itself, before our app, so our framing header never
  reached them); BotID's old Next.js wrapper (its rewrites are no longer needed: Vercel routes those paths); and the
  chat skipping BotID's hook (it uses the page's `fetch` when it sends).
- **Not visible:** why. Vercel shows BotID's reasons only with Observability Plus, a paid add-on.

**The main suspect:** both tabs were in the same Chrome profile, which has a browser-automation extension installed
(the one our tools drive Chrome with). BotID is built to spot automation, so it may have been flagging the extension;
a browser without it may pass. Not yet proven: the second tab was yours, but in the same profile, so it didn't rule
the extension out.

**The plan:**

1. **BotID back on, watching only:** the server logs BotID's full verdict, its reason included, and refuses no one.
2. **Two messages:** one from the usual Chrome, one from a browser without the extension: Edge, or a Chrome Incognito
   window, where extensions are off unless allowed there (check the extension's own setting first). Their two verdicts
   show whether the extension is the cause.
3. **Refusing again** only once a browser without the extension passes, and only with a check after every deploy that
   sends one real message through the real page: the browser tests never ask the server.

**The risk while it watches:** BotID's page script comes back, and if Vercel ever failed to serve it, a message would
fail; it loaded fine before. And its 3 s would take a request's worst case to 62 s, past the function's 60, so a
budget shrinks first: the answer's 50 s to 47, or the connection's 6 s to 5 (entry 122).

## The rest of step 8

- **Enforce the Content Security Policy.** It only reports for now: a browser test fails on any report, but that test
  hasn't yet run against the live site with BotID on. It's enforced once BotID's state is settled, with the test run
  against the live site first.
- **Check the firewall rules,** once they're set: the 21st request in a minute gets `429`, and the chat's own calls
  to `/api/mcp` aren't limited.

## The next steps in the plan

| Step | What | Why |
|---|---|---|
| 9 · Observability | Done: the log lines to Axiom, the errors to Sentry, the source maps (part 1). Next: `/api/health` for the four lanes and the lanes' status dots (part 2); then dashboards, alerts, traces and an uptime monitor (part 3) | To know the app is down before a user says so; the health check also checks Apify's token without running anything (PLAN.md section 3, row 14) |
| 10 · Evals and failure tests | The golden questions on all four lanes, with the comparison report; the `CHAOS` setting to play failures on a preview, and Playwright on previews in CI; the no-auth lanes' cache fallback and the amber "slow, retrying" chip, both moved from step 5; a daily check of Apify's tool list against our pin; a load test | To catch a model, a third party or a change going wrong before users do |
| 11 · Launch | Production settings, the paid model path, the README finished in project 01's shape, the runbook and the demo | The free tier's terms don't fit a public app, and a launch needs its runbook |
| 12 · OAuth 2.1 + PKCE | "Connect your Apify account" for `MCP · with auth`, through `@ai-sdk/mcp`'s auth provider | So a user's own Apify account pays for their runs, instead of the bot's token |
| 13 · Later | Voice input (the mic, blocked until then), past weather, more languages, and a second data source | Voice and more languages reach more people; with a second source, one upstream's outage doesn't stop every lane |

## Smaller follow-ups

- **A lighter Sentry** (bug story 18): on a laptop, Sentry makes a cold start about 2.4 s slower, most of it from its
  build step (`withSentryConfig`): without the build step, a cold start measured 1.3 s against 3.1 s, and errors still
  reach Sentry; the source maps would then be uploaded by Sentry's own command in the build. On Vercel, its share
  isn't measured apart yet. For now, connecting to our MCP server gets 6 s instead of 3, so a cold first question
  should no longer fail.
- **Sentry's first event from the live site:** nothing there fails at `error` on demand, so the path is first checked
  by a real error, or by step 10's forced `AuthError` (`CHAOS`).
- **`npm audit` reports 4 "high" findings,** all one old zod (4.1.11) deep in `@vercel/functions`, which reads only the
  Vercel CLI's own files, never a user's input. An npm override, or `@vercel/functions`' next release, clears them;
  PLAN.md 9.4's audit in CI waits on it (entry 118).
- **Stop, heard late early in an answer:** in one live check, a hang-up right after the first bytes reached the
  function about 7 s later, where one during the answer's text was heard at once (bug story 16). Why Vercel notices
  late is open.
- **Vercel's log view lists some lines twice** for a cancelled request (entry 102): step 9's dashboards should count
  an answer's endings by request id, not by line.
- **Live checks need the bypass header once BotID refuses scripts:** the evals send it, when
  `VERCEL_AUTOMATION_BYPASS_SECRET` is set; the live-check scripts will need it too, once the firewall's bypass rule
  is set.
