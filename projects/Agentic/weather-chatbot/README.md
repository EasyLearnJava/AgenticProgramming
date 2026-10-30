# Weather Chatbot (Nimbus)

> **Status:** steps 1 to 7 of the [plan](PLAN.md) are done: the project skeleton, the chat page, the live chat
> through `REST · no auth`, `MCP · no auth` through our own MCP server, errors and logs, `REST · with auth` through
> Apify's weather Actor, with a token, and `MCP · with auth`, the same Actor through Apify's MCP server. Step 8 is
> built: BotID on the chat and the security headers; its firewall rules are set in Vercel's dashboard. Live at
> https://weather-chatbot-hazel.vercel.app/ (the chat needs your Gemini key in Vercel's settings, and the auth lanes
> an Apify token: [Deploy it on Vercel](#deploy-it-on-vercel)).

Nimbus is a weather chatbot on Vercel. You ask about the weather in plain words and see every tool call it makes,
through four lanes: REST or MCP, with or without auth. Gemini calls our four weather tools, either directly
(`REST · no auth`) or through our own MCP server at `/api/mcp` (`MCP · no auth`, the default), and they call
Open-Meteo; on the auth lanes, the forecast comes from an Apify Actor instead, with a token, through Apify's REST API
(`REST · with auth`) or its MCP server (`MCP · with auth`), and falls back to the no-auth lane behind the same door
when Apify can't answer. Each call shows as a chip that opens to show its request, and a
forecast gets a weather card. A left menu leads to the documentation, one page per finished build step.

**In one line:** a question → `useChat` posts it to `/api/chat` → the route checks it → Gemini, with our four tools →
each tool calls Open-Meteo, itself (REST) or through `/api/mcp` (MCP), or, for `REST · with auth`'s forecast, runs
Apify's Actor → the answer streams back, with a chip per tool call.

## Documentation

The app explains itself: open **Documentation** in its left menu, or read the same pages in [`docs/`](docs/). There's
one page per build step: what it built, how it works, and how to check it. **System design**, also in the menu
([`docs/system-design.md`](docs/system-design.md)), draws how the app is built today, in the four bands of a common
reference design for AI assistants, and sets each part against it. **Issues and fixes**
([`docs/issues.md`](docs/issues.md)) logs every problem met while building and deploying it, and how it was fixed;
it opens with the real bugs, each told as a story.

## Before you start

- Node.js 22: the version Vercel runs this project on (`engines` in `package.json`)
- npm
- A Gemini API key, the one the repo's other projects use, for the chat itself (the page and the tests run without it)
- An Apify API token, only for the auth lanes (the no-auth lanes run without it)

## How it's organised

| Folder or file | What's in it |
|---|---|
| `app/` | The pages: the chat (`page.tsx`), the documentation (`docs/`), the system design (`system-design/`), the issues log (`issues/`), the 404 page (`not-found.tsx`), the shell around them (`layout.tsx`), and every style (`globals.css`); the endpoints in `api/`: the chat (`chat/`), our MCP server (`mcp/`) and the nearby city (`nearby-city/`) |
| `components/` | The React components: the left menu, the Markdown viewers (documentation, answers), the system design's diagram, and the chat's parts (the chat window, the welcome, the lane picker, a message, a tool chip, the weather card, the input, the compare view) |
| `hooks/` | The React hook that asks for the nearby city |
| `lib/` | The settings (`config.ts`, the only reader of environment variables), the shared types, constants and helpers (`types.ts`, `constants.ts`, `utils.ts`), the error map and the logger (`errors.ts`, `logger.ts`); the chat (`chat/`: the request's rules, the model, the system prompt, one chat turn), the lanes (`lanes/`), the calls to Open-Meteo and Apify (`upstream/`), the weather tools (`weather/`), and the documentation's list, reader and system design diagram (`docs/`) |
| `docs/` | The documentation pages, one Markdown file per step, the system design (`system-design.md`) and the issues log (`issues.md`) |
| `tests/` | The unit tests (`unit/`), Open-Meteo's and Apify's recorded answers (`fixtures/`), the end-to-end tests in a real browser (`e2e/`), the golden questions (`evals/`), and stand-ins the unit tests need (`stubs/`) |
| `PLAN.md` | The plan for the whole build |
| Settings files | `package.json` (scripts, exact versions), `tsconfig.json`, `biome.json`, `vitest.config.ts`, `vitest.evals.config.ts`, `playwright.config.ts`, `next.config.ts` (the security headers), `instrumentation-client.ts` (BotID's page side), `vercel.json` (Vercel tells the chat when the page goes), `.env.example`, `.npmrc`, `.gitignore`, `.gitattributes` |

CI lives at the repository's root, in `.github/workflows/weather-chatbot.yml`.

## Run it

From the repo's root:

```bash
cd projects/Agentic/weather-chatbot
npm install
cp .env.example .env.local
npm run dev
```

```text
▲ Next.js 16.4.3 (Turbopack)
- Local:         http://localhost:3000
✓ Ready in 578ms
✓ Running next.config.ts took 54ms
```

(A `Network:` line with your machine's address is left out.) Open `.env.local` in an editor and put your Gemini key
after `GOOGLE_API_KEY=`, and, for the auth lanes, an Apify token after `APIFY_TOKEN=`; the file never goes into
git. Then open http://localhost:3000: the chat card with Nimbus's first message and questions to try, the menu on the
left and `Build: local` at its foot. Ask the Paris question, and open the `get_forecast` chip to see the request it
sent. Without the key, the page says the chat isn't set up yet.
`npm run build`, then `npm run start`, serves the production build instead.

## Test it

```bash
npm run lint        # Biome: formatting, and the naming and coding rules; a warning fails it too
npm run typecheck   # Next.js's route types, then TypeScript in strict mode
npm test            # the unit tests, with Vitest
npm run build       # the production build
npm run e2e         # the end-to-end tests: Playwright, in a real browser, on a desktop and a phone screen
npm run evals       # against a running deployment (EVAL_BASE_URL): the golden questions, and the MCP server
```

```text
$ npm run lint
Checked 116 files in 296ms. No fixes applied.

$ npm run typecheck
Generating route types...
✓ Types generated successfully

$ npm test
 Test Files  36 passed (36)
      Tests  255 passed (255)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Running next.config.ts took 36ms
  Creating an optimized production build ...
✓ Compiled successfully in 1630ms
  Running TypeScript ...
  Finished TypeScript in 399ms ...
  Collecting page data using 11 workers ...
  Generating static pages using 11 workers (0/17) ...
✓ Generating static pages using 11 workers (17/17) in 1732ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /api/chat
├ ƒ /api/mcp
├ ƒ /api/nearby-city
├ ○ /docs
├   /docs/[slug]
│ ├ ● /docs/step-1
│ ├ ● /docs/step-2
│ ├ ● /docs/step-3
│ └ ● [+5 more paths]
├ ○ /issues
└ ○ /system-design

○  (Static)   prerendered as static content
●  (SSG)      prerendered as static HTML (uses generateStaticParams)
ƒ  (Dynamic)  server-rendered on demand

$ npm run e2e
  50 passed (20.4s)
```

npm also prints each script's name and command first, Vitest a start time and duration, Next.js a line per batch of
pages, and Playwright one line per test; those are left out here. The times change from run to run. None of these
calls a model: the unit tests use AI SDK's mock model and Open-Meteo's recorded answers, and the end-to-end tests
answer the page's `/api/chat` with a recorded answer. `npm run e2e` serves the build that `npm run build`
made and tests it in Playwright's Chromium (install it once: `npx playwright install chromium`; or set
`E2E_BROWSER_CHANNEL=msedge` to use an installed Edge). With `BASE_URL` set (for example
`https://weather-chatbot-hazel.vercel.app`) it tests that site instead. GitHub runs all five on every push that
touches this folder. `npm run evals` asks a running deployment the golden questions, so its real model answers
(`EVAL_BASE_URL=https://weather-chatbot-hazel.vercel.app npm run evals`), on each lane in `EVAL_LANES` (both no-auth
lanes by default), and checks the MCP server as any MCP client would; it runs by hand, not in CI. On a machine whose
HTTPS goes through its own certificate, add `NODE_OPTIONS=--use-system-ca` so Node trusts the system's certificates.

## Deploy it on Vercel

1. In Vercel, choose **Add New → Project** and import the GitHub repository `EasyLearnJava/AgenticProgramming`.
2. Set **Root Directory** to `projects/Agentic/weather-chatbot`. Vercel detects Next.js; keep the default build
   settings.
3. Choose **Deploy**. The Node.js version comes from `package.json` (`22.x`), and `vercel.json` turns on request
   cancellation for the chat route, so that Vercel tells the chat when the page goes (issue 101).
4. In the project's settings, set **Ignored Build Step** to `git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .`.
   Vercel runs it in the Root Directory: it exits with 0 (skip the build) only when nothing in this folder changed
   since the last successful deployment. On the first deployment the variable is empty, so `git` fails, and Vercel
   builds. (Vercel's own "Skip deployments" switch doesn't help here: it needs npm, Yarn, pnpm or Bun workspaces,
   which this repository doesn't have, so without this command every push to `main` rebuilds the app.)
5. In **Settings → Environment Variables**, add `GOOGLE_API_KEY` with your Gemini key, for Production and Preview;
   then redeploy, since a deployment keeps the settings it was built with. Without it, the chat answers that it isn't
   set up yet.
6. For the auth lanes, make a token in an Apify account used only for this bot, since the token opens the whole
   account (Apify Console: **Settings → API & Integrations**). Add it as `APIFY_TOKEN`, type **Secret**, then
   redeploy: the chat page reads whether it's set when the deployment is built. Without it, the picker says the auth
   lanes need a token.
7. For step 8's protection, in the project's **Firewall**, add two custom rules, in this order, and publish them.
   First, a **bypass**: a request whose header `x-vercel-protection-bypass` equals the project's Protection Bypass for
   Automation secret skips the rules after it, and BotID; the chat's own calls to `/api/mcp` carry it. Second, a
   **rate limit**: a request whose path starts with `/api/`, 20 a minute per IP address, then denied with `429`.
   BotID itself needs no setting.

## Read the logs

Each request logs a few JSON lines (pino, to stdout), which Vercel shows under **Logs** in the project's dashboard:
one when it starts (`chat.request`), one per hop (connecting to MCP, each tool call, each call to Open-Meteo, each
model step; on the auth lanes, each call to Apify, `upstream.http` or `upstream.mcp`, and `lane.fallback` when one
falls back), and one when
it ends (`chat.done`, or how it stopped or failed). Every line carries the request's id;
`MCP · no auth` sends it on to `/api/mcp`, so the server's lines carry it too. When the page shows an error, its
sentence ends with the ref, the id's last 8 characters: search the logs for it. `LOG_LEVEL` (`info` unless set) says
how much to log. A line never holds your question (only its length), a token or a key.

## Use the MCP server

`/api/mcp` is a public MCP server with the four weather tools; any MCP client that speaks Streamable HTTP can use it,
for example in Claude or Cursor:

```json
{ "nimbus-weather": { "url": "https://weather-chatbot-hazel.vercel.app/api/mcp" } }
```

## Next

Step 8's live check, then its Content Security Policy enforced and the firewall rules checked once you've set them;
then step 9 in [PLAN.md](PLAN.md): observability.
