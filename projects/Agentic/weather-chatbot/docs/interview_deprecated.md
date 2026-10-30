# Interview Guide

What to tell an interviewer about Nimbus: what it is, the decisions that make it production grade, and the incidents
worth telling, each with what went wrong, why, how it was found, how it was fixed and what it taught. Every number here
comes from the code, the live site or the tests, and every story is told in full in **Issues and fixes**.

## The pitch, in 30 seconds

Nimbus is a weather chatbot on Vercel that shows its work. You ask in plain words; Gemini calls weather tools, and each
call appears as a chip you can open to see the exact request that went out. The point is a comparison: the same tools
reach the weather through four lanes, REST or MCP, without auth or with a token. Two lanes call Open-Meteo, directly or
through an MCP server we built; two run a paid Apify Actor, through Apify's REST API or its MCP server. An auth lane
that fails falls back to its free twin and says so. It's built step by step: every change reviewed before its commit
(but one emergency switch, reviewed just after), checked on the live site after its deploy, and every problem logged
with its fix.

## What makes it production grade

- **One request, followed end to end.** Every request gets an id (Vercel's own), every log line carries it, our MCP
  server's lines too, and an error's sentence ends with its last 8 characters, so a user's screenshot finds the logs,
  kept in Axiom, and the error, in Sentry, where the ref is a tag.
- **Observability that keeps the question private.** The lines go to Axiom in one batch at each request's end, kept
  alive past the answer by `waitUntil`; errors go to Sentry, whose version 11 collects bodies, headers and AI prompts
  unless told not to, so each is turned off, and its trace headers stay off our calls to other services. And
  `/api/health` checks each lane's ways out without running anything that costs; each lane shows it as a dot, and a
  monitor can watch it. Every request is traced, through both functions, under its id, with every query string cut
  from the spans, since an address's query can hold the place a user typed.
- **Time budgets on every hop.** 50 s for an answer (the function stops at 60), 10 s for the model's first chunk, 8 s
  for a tool, 20 s for an Actor run (25 on MCP, which may connect first), 6 s to connect to our MCP server (3 s until
  a cold start needed more: bug story 18) and 5 s to
  Apify's. A fallback
  starts only with 12 s left, so it can finish; the slowest path was worked out: 41 s of the 50.
- **Errors as types, not strings.** Each failure is one of our classes, which decides its HTTP status, the sentence the
  user sees, its log level and whether a retry may help. Upstream text never reaches the page.
- **Bounded cost and supply chain.** Both doors to the paid Actor pin its build, cap a run at 18 s and $0.01, and a
  test holds the two doors to the same limits. The token goes only in a header, is masked in every view and log, and
  the app never pays Apify's `402`. A run costs $0.005.
- **Honest fallbacks.** When Apify can't answer, the free twin does, and the chip says why ("Apify took too long").
- **MCP both ways.** Our own MCP server (stateless, protocol 2026-07-28), which takes one message per request, at most
  8 KB (bug story 4), and an MCP client of Apify's server (2025-11-25, with sessions), whose tool list is checked
  against a pin before use.
- **Streaming done right.** The lane closes once the answer's stream has ended, however it ends; an answer logs
  exactly one ending; and Stop reaches the function on Vercel, where it had to be turned on.
- **Security in layers.** Security headers on every response; a Content Security Policy introduced in report-only mode,
  with a browser test that fails on any report; input limits checked with Zod; read-only tools, Markdown without raw
  HTML or images, so a tool's output can't carry the chat away; and a bot check on the chat, built with a kill switch,
  and switched off for now (bug story 17).
- **Tests that can fail.** 292 unit tests and 58 browser tests (with accessibility, a phone's width, and the policy's
  reports), golden questions asked of the live site, and CI on every push. Since step 7, new tests are checked by
  breaking the code they guard ("mutation checks"): each must fail without its fix.
- **Process.** An independent reviewer reads every change before its commit (all but one emergency switch, read just
  after); every deploy is checked on the live site; every problem goes in the issues log (141 entries), and the real
  bugs become stories.

## The stories to tell

Each is a bug story in **Issues and fixes**; here is the short version, in the order an interview might want them.

### The health check that blamed the live site (bug story 19)

- **What happened:** as each deploy went out, something loaded the new deployment at its own, protected address, from
  Vercel's `sfo1` region; its health check called our MCP server through that address, got Vercel's `401`, and said
  the MCP lanes were down. The
  route kept one result per copy of the function for a minute, whatever the address, so the live site's dots could
  have shown those lanes as not answering for a minute after a deploy.
- **How it was found:** within the hour, in the new logs: `health.done` said `down` at each deploy, from Vercel's
  `sfo1` region, with the `401` as the failed check's cause.
- **How it was fixed:** one result per address, and each health line names its origin, so an alert can watch the
  live site alone.
- **The lesson:** key a cache by everything its answer depends on; and read the logs right after a deploy.

### The slowness that crossed six services (bug story 18)

- **What happened:** right after the logs went to Axiom and the errors to Sentry, the first question on the live site
  failed in 4.4 s ("took too long"), and the next answers took 36 to 50 s.
- **Why it was hard:** a question's path crosses six services (Vercel's two functions, Gemini, Open-Meteo, Axiom and
  Sentry), and any of them could be the slow one; two were, at once.
- **How it was noticed:** the check after every deploy asks the live site a real question (bug story 17's lesson).
- **How the cause was found:** each hop timed apart. Another lane, without the MCP hop: slow too. Each chunk of the
  stream: the model's steps took 27, 6 and 3 s, the tools milliseconds. The new logs in Axiom, one request id across
  both functions: the connection to our MCP server didn't finish within its 3 s budget. The same code an hour later:
  fast, so the slow steps were Gemini's bad hour. A cold and a warm MCP server: 1.9 s and 0.4 s. And the app built
  with and without Sentry, started cold on a laptop: 0.7 s without it, 3.1 s with it.
- **How it was fixed:** the connection's budget went from 3 s to 6 s, so a cold first question no longer fails: after
  the fix's deploy, the first question, both functions cold, connected in 4.2 s and answered in 9.2 s. A lighter
  Sentry, without its build step (1.3 s on the laptop), is next.
- **The lesson:** time the cold start before and after adding an SDK; cut a slow request into hops and time each one;
  run the same code again later to tell a provider's bad hour from your own change.

### The bot check that blocked every user (bug story 17)

- **What happened:** after step 8 added Vercel's BotID to the chat, every message we sent got "We couldn't verify this
  browser", for about 25 minutes, from one Chrome profile in two tabs: one our tools drove, one the user's own.
- **Why it slipped through:** the browser tests answer `/api/chat` inside the page, so no test sent a real message
  through BotID to the server; the deploy check only read the build line.
- **How it was found:** the post-deploy check sent one real message from a real browser, and the user confirmed it
  from theirs.
- **How it was fixed:** a one-line kill switch turned BotID off everywhere; the chat answered again within minutes,
  and the security headers stayed. Why real browsers failed BotID's check is still being traced; BotID comes back in
  a watching mode first, logging its verdicts and refusing no one.
- **The lesson:** roll out anything that can refuse users in a watching mode first, keep a kill switch, and check
  every deploy with a real request on the real path: mocks can't see it.

### Stop that didn't stop (bug story 16)

- **What happened:** on Vercel, pressing Stop left the model, the tools and any paid Actor run going to the end.
- **Why:** Vercel tells a function that its caller has gone only when cancellation is turned on for it; a local
  Next.js server does it by default, which is what the code and the tests had assumed.
- **How it was fixed and proven:** cancellation turned on for the chat route; the function kept alive (`waitUntil`)
  just long enough to write its last line and close its connections. Live, a hang-up mid-answer now ends with
  `chat.aborted` instead of `chat.done`.
- **The lesson:** the platform is part of the behavior; check what Stop does where the code runs.

### An error part closed the connection mid-answer (bug story 15)

- **What happened:** the chat closed its MCP connection on the first error part of a stream, but the model can go on
  after one and call tools, which would have met a closed connection.
- **The fix:** close on the stream's own end, which fires however the answer ends. A reviewer suggested stopping the
  run at the error instead; a test showed that dropped the error message the user needed, so it was rejected.
- **The lesson:** tie clean-up to the end of the stream, and test a suggestion before taking it.

### The MCP door that would have run any build (bug story 14)

- **What happened:** as first written, the MCP lane ran the Actor through a tool that takes no build, time or cost
  limit, while the REST door pinned all three.
- **The fix:** Apify's `call-actor` takes the same limits; the lane uses it, and a test holds the two doors to the same
  build, time and cost. Apify Console confirmed the time and cost limits on a live run (the build pinned is also the
  Actor's latest, so the pin itself can't show yet).
- **The lesson:** "can't" is a claim; check it, and test twin paths against each other.

### The Actor's answer wasn't the shape we assumed (bug story 12)

- **What happened:** the first live run returned one item per day, not one per place, and the lane refused it.
- **The fix:** read the real shape, kept as a fixture from the live run, with tests against it.
- **The lesson:** a third party's real answer is the spec; record it and test against it.

## Numbers worth quoting

| What | Number |
|---|---|
| A forecast through Apify's REST door, and through its MCP door | 3.6 s and 10.5 s, live (Apify's MCP server waits up to 5 s after a run for its items) |
| One Actor run | $0.005, 2 to 4 s |
| A hop to our own MCP server | about 0.1 s a tool call, plus one connection per answer (0.2 to 1.8 s) |
| Stop, heard by the function | at once during the answer's text; about 7 s after a hang-up early in the answer (one live check each) |
| BotID's outage | about 25 minutes, ended by a one-line switch |
| A cold start, with Sentry | on a laptop, about 2.4 s more on the first request (3.1 s with Sentry, 0.7 s without); on Vercel, a cold MCP connection took 4.2 s inside the chat with it, 1.1 to 1.8 s before step 9 |
| The health check, live | four checks, each lane `ok`; our MCP server's cold connection 4.0 s; the CDN's kept answer 0.37 s |
| Gemini's slow hour | steps of 3 to 27 s, against about 1 s or less; the same code an hour later answered in 2.4 to 3.9 s |
| Tests | 292 unit, 58 browser, golden questions on the live site |

## Questions you may get

- **Why both REST and MCP?** To show what MCP adds and costs on the same task: discovery of tools and a protocol any
  client can use, at the price of a handshake and a hop. The compare view shows the same call through each door.
- **How do you stop a third party from taking you down?** Time budgets on every call, typed errors, a fallback with
  time left to finish, and pins that refuse a changed contract instead of guessing.
- **How do you keep costs bounded?** Caps per run sent with every call, a pinned build, never paying a `402`, and the
  free tier's quota as the model's cap until launch.
- **How do you know a test tests the right thing?** Break the code it guards and watch it fail; since step 7, every
  new test here has been checked that way.
- **What would you do differently?** Roll out protections in watching mode first; and from day one, check every deploy
  with one real request on the real path, since mocked browser tests can't see the server's side.
- **How do you find what's slow when a request crosses many services?** Cut its path into hops and time each one: the
  answer's stream chunk by chunk, and every hop's log line under one request id. Compare cold with warm, and the same
  code at another hour, before blaming a change; then A/B the suspect: the app built with and without it (bug
  story 18).

## What's next

Find why BotID refuses real browsers, then turn it back on; enforce the Content Security Policy; the firewall rules;
and the rest of observability (step 9): a health check and status dots, then dashboards, alerts and traces.
