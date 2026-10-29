# Issues and Fixes

Every problem we met while building and deploying Nimbus, and how it was fixed. Each build step adds its own, in
the same change as its code; the newest step is last. An entry says what happened and why, then the fix, and what
now checks it, so it can't quietly come back. *Found by* says how it surfaced: **testing a real API**, **checking our
work** (the type check, the tests, screenshots, contrast), the **review** that every step gets from an independent
reviewer before its commit, **reading a package's code**, or **deploying**.

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

4. **Empty settings failed the settings check.** *Review.* `vercel env pull` writes some variables as empty strings,
   and an empty `VERCEL_ENV` broke the settings check that runs when the app starts. **Fix:** an empty value counts as
   missing (`lib/config.ts`). **Check:** `tests/unit/config.test.ts`.
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
38. **The key had to be set up on Vercel.** *Deploying.* The chat reads `GOOGLE_API_KEY` from Vercel's settings. It
    was added as a Sensitive variable, so its value can't be read back from the dashboard, for Production only. We
    checked it by name, not by value. Preview deployments won't have it: tick Preview too, to chat on them. A setting
    reaches the next deployment, not the running one.
