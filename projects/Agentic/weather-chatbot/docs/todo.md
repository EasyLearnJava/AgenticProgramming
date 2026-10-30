# To Do

What's still open, and why: first what waits on you, then BotID, then the rest of the plan. Each item says what it
needs and what it's for. Steps 1 to 7 are done and checked on the live site; step 8 is partly done.

## Waiting on you

| What | Why it's needed | Where |
|---|---|---|
| The two firewall rules: a bypass, then a rate limit of 20 requests a minute on `/api/*` | The rate limit caps abuse, and matters more while BotID is off; the bypass lets the chat's own calls to `/api/mcp` through, and later our evals past BotID | README, "Deploy it on Vercel", step 7 |
| An Axiom account, and a Sentry account | Step 9: Vercel's Hobby plan keeps logs only an hour and can't forward them, so Axiom stores and searches them; Sentry collects each error with its stack trace and alerts on it | axiom.co, sentry.io |
| The Ignored Build Step, in Vercel's project settings | Without it, every push to the repository rebuilds the app, even when nothing in its folder changed | README, "Deploy it on Vercel", step 4 |
| `GOOGLE_API_KEY` and `APIFY_TOKEN` for Preview deployments | Previews can't chat without them; today they're set for Production only | Vercel, Settings, Environment Variables |
| The paid model path, before the URL is public | Gemini's free tier may use prompts to improve Google's products, and serving users in the EEA, Switzerland or the UK needs the paid service | PLAN.md, decision 3 (step 11) |

## BotID, switched off

Step 8 put Vercel's BotID in front of the chat, and on the live site it refused every message we sent, from two real
browsers, for about 25 minutes. It has been off since `810a981`; the chat has no bot check meanwhile (bug story 17,
entry 111).

**What's known:**

- **The page side worked:** BotID's script loaded from our own address, and the page's requests went through BotID's
  hook, so each message carried BotID's answer.
- **The answer reached the server:** BotID logs a warning when a request comes without one, and it did so only for a
  script we ran, not for the browsers' messages. So Vercel's check read the browsers' answers and still called them
  bots.
- **Ruled out:** our security headers (Vercel serves BotID's paths itself, before our app, so our framing header never
  reached them); BotID's old Next.js wrapper (its rewrites are no longer needed: Vercel routes those paths); and the
  chat skipping BotID's hook (it uses the page's `fetch` when it sends).
- **Not visible:** why. Vercel shows BotID's reasons only with Observability Plus, a paid add-on.

**The main suspect:** both refused browsers were the same Chrome profile, one with a browser-automation extension
installed (the one our tools drive Chrome with). BotID is built to spot automation, so it may have been flagging the
extension; a browser without it may pass. Not yet proven.

**The plan:**

1. **BotID back on, watching only:** the server logs BotID's full verdict, its reason included, and refuses no one.
2. **Two messages:** one from the usual Chrome, one from a browser without the extension (Edge, or a Chrome Incognito
   window, where extensions are off). Their two verdicts show whether the extension is the cause.
3. **Refusing again** only once a browser without the extension passes, and only with a check after every deploy that
   sends one real message through the real page: the browser tests never ask the server.

**The risk while it watches:** BotID's page script comes back, and if Vercel ever failed to serve it, a message would
fail; it loaded fine before.

## The rest of step 8

- **Enforce the Content Security Policy.** It only reports for now: a browser test fails on any report, and found none
  on the live site with BotID's script. It's enforced once BotID's state is settled, with that test run against the
  live site again.
- **Check the firewall rules,** once they're set: the 21st request in a minute gets `429`, and the chat's own calls
  to `/api/mcp` aren't limited.

## The next steps in the plan

| Step | What | Why |
|---|---|---|
| 9 · Observability | Logs shipped to Axiom, Sentry for errors, traces, dashboards, alerts, `/api/health` for the four lanes, the lanes' status dots, an uptime monitor | To know the app is down before a user says so; the health check also checks Apify's token without running anything (PLAN.md section 3, row 14) |
| 10 · Evals and failure tests | The golden questions on all four lanes, the `CHAOS` setting to play failures on a preview, a daily check of Apify's tool list against our pin, a load test | To catch a model, a third party or a change going wrong before users do |
| 11 · Launch | Production settings, and the paid model path | The free tier's terms don't fit a public app |
| 12 · OAuth 2.1 + PKCE | "Connect your Apify account" for `MCP · with auth`, through `@ai-sdk/mcp`'s auth provider | So a user's own Apify account pays for their runs, instead of the bot's token |
| 13 · Later | Voice input (the mic, blocked until then), past weather, a second data source | Nice to have |

## Smaller follow-ups

- **Stop, heard late early in an answer:** in one live check, a hang-up right after the first bytes reached the
  function about 7 s later, where one during the answer's text was heard at once (bug story 16). Why Vercel notices
  late is open.
- **Vercel's log view lists some lines twice** for a cancelled request (entry 102): step 9's dashboards should count
  an answer's endings by request id, not by line.
- **Live checks need the bypass header once BotID refuses scripts:** the evals and our live-check scripts send it, so
  they work once the firewall's bypass rule is set.
