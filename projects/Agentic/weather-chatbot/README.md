# Weather Chatbot (Nimbus)

> **Status:** steps 1 and 2 of the [plan](PLAN.md) are done: the project skeleton and the chat page. Step 3, the live
> chat through the first lane, `REST · no auth`, is built and waits for its live check. Live at
> https://weather-chatbot-hazel.vercel.app/ (the chat needs your Gemini key in Vercel's settings:
> [Deploy it on Vercel](#deploy-it-on-vercel)).

Nimbus is a weather chatbot on Vercel. You ask about the weather in plain words and see every tool call it makes,
through four lanes: REST or MCP, with or without auth. Today one lane is live: Gemini calls our four weather tools,
which call Open-Meteo's API directly. Each call shows as a chip that opens to show its request, and a forecast gets a
weather card. A left menu leads to the documentation, one page per finished build step.

**In one line:** a question → `useChat` posts it to `/api/chat` → the route checks it → Gemini, with our four tools →
each tool calls Open-Meteo → the answer streams back, with a chip per tool call.

## Documentation

The app explains itself: open **Documentation** in its left menu, or read the same pages in [`docs/`](docs/). There's
one page per build step: what it built, how it works, and how to check it. **Issues and fixes**, also in the menu
([`docs/issues.md`](docs/issues.md)), logs every problem met while building and deploying it, and how it was fixed.

## Before you start

- Node.js 22: the version Vercel runs this project on (`engines` in `package.json`)
- npm
- A Gemini API key, the one the repo's other projects use, for the chat itself (the page and the tests run without it)

## How it's organised

| Folder or file | What's in it |
|---|---|
| `app/` | The pages: the chat (`page.tsx`), the documentation (`docs/`), the issues log (`issues/`), the 404 page (`not-found.tsx`), the shell around them (`layout.tsx`), and every style (`globals.css`); the endpoints in `api/`: the chat (`chat/`) and the nearby city (`nearby-city/`) |
| `components/` | The React components: the left menu, the Markdown viewers (documentation, answers), and the chat's parts (the chat window, the welcome, the lane picker, a message, a tool chip, the weather card, the input, the compare view) |
| `hooks/` | The React hook that asks for the nearby city |
| `lib/` | The settings (`config.ts`, the only reader of environment variables), the shared types, constants and helpers (`types.ts`, `constants.ts`, `utils.ts`), the error classes and the logger (`errors.ts`, `logger.ts`); the chat (`chat/`: the request's rules, the model, the system prompt, one chat turn), the lanes (`lanes/`), the calls to Open-Meteo (`upstream/`), the weather tools (`weather/`), and the documentation's list and reader (`docs/`) |
| `docs/` | The documentation pages, one Markdown file per step, and the issues log (`issues.md`) |
| `tests/` | The unit tests (`unit/`), Open-Meteo's recorded answers (`fixtures/`), the end-to-end tests in a real browser (`e2e/`), the golden questions (`evals/`), and stand-ins the unit tests need (`stubs/`) |
| `PLAN.md` | The plan for the whole build |
| Settings files | `package.json` (scripts, exact versions), `tsconfig.json`, `biome.json`, `vitest.config.ts`, `vitest.evals.config.ts`, `playwright.config.ts`, `next.config.ts`, `.env.example`, `.npmrc`, `.gitignore`, `.gitattributes` |

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
after `GOOGLE_API_KEY=`; it never goes into git. Then open http://localhost:3000: the chat card with Nimbus's first
message and questions to try, the menu on the left and `Build: local` at its foot. Ask the Paris question, and open
the `get_forecast` chip to see the request it sent. Without the key, the page says the chat isn't set up yet.
`npm run build`, then `npm run start`, serves the production build instead.

## Test it

```bash
npm run lint        # Biome: formatting, and the naming and coding rules; a warning fails it too
npm run typecheck   # Next.js's route types, then TypeScript in strict mode
npm test            # the unit tests, with Vitest
npm run build       # the production build
npm run e2e         # the end-to-end tests: Playwright, in a real browser, on a desktop and a phone screen
npm run evals       # the golden questions, against a running deployment (EVAL_BASE_URL); skipped without it
```

```text
$ npm run lint
Checked 80 files in 398ms. No fixes applied.

$ npm run typecheck
Generating route types...
✓ Types generated successfully

$ npm test
 Test Files  21 passed (21)
      Tests  100 passed (100)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Running next.config.ts took 73ms
  Creating an optimized production build ...
✓ Compiled successfully in 903ms
  Running TypeScript ...
  Finished TypeScript in 571ms ...
  Collecting page data using 9 workers ...
  Generating static pages using 9 workers (0/10) ...
✓ Generating static pages using 9 workers (10/10) in 1517ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /api/chat
├ ƒ /api/nearby-city
├ ○ /docs
├   /docs/[slug]
│ ├ ● /docs/step-1
│ ├ ● /docs/step-2
│ └ ● /docs/step-3
└ ○ /issues

○  (Static)   prerendered as static content
●  (SSG)      prerendered as static HTML (uses generateStaticParams)
ƒ  (Dynamic)  server-rendered on demand

$ npm run e2e
  38 passed (15.8s)
```

npm also prints each script's name and command first, Vitest a start time and duration, Next.js a line per batch of
pages, and Playwright one line per test; those are left out here. The times change from run to run. None of these
calls a model: the unit tests use AI SDK's mock model and Open-Meteo's recorded answers, and the end-to-end tests
answer the page's `/api/chat` with a recorded answer. `npm run e2e` serves the build that `npm run build`
made and tests it in Playwright's Chromium (install it once: `npx playwright install chromium`; or set
`E2E_BROWSER_CHANNEL=msedge` to use an installed Edge). With `BASE_URL` set (for example
`https://weather-chatbot-hazel.vercel.app`) it tests that site instead. GitHub runs all five on every push that
touches this folder. `npm run evals` asks a running deployment the golden questions, so its real model answers
(`EVAL_BASE_URL=https://weather-chatbot-hazel.vercel.app npm run evals`); it runs by hand, not in CI.

## Deploy it on Vercel

1. In Vercel, choose **Add New → Project** and import the GitHub repository `EasyLearnJava/AgenticProgramming`.
2. Set **Root Directory** to `projects/Agentic/weather-chatbot`. Vercel detects Next.js; keep the default build
   settings.
3. Choose **Deploy**. The Node.js version comes from `package.json` (`22.x`).
4. In the project's settings, set **Ignored Build Step** to `git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .`.
   Vercel runs it in the Root Directory: it exits with 0 (skip the build) only when nothing in this folder changed
   since the last successful deployment. On the first deployment the variable is empty, so `git` fails, and Vercel
   builds. (Vercel's own "Skip deployments" switch doesn't help here: it needs npm, Yarn, pnpm or Bun workspaces,
   which this repository doesn't have, so without this command every push to `main` rebuilds the app.)
5. In **Settings → Environment Variables**, add `GOOGLE_API_KEY` with your Gemini key, for Production and Preview;
   then redeploy, since a deployment keeps the settings it was built with. Without it, the chat answers that it isn't
   set up yet.

## Next

Step 4 in [PLAN.md](PLAN.md): `MCP · no auth`. Our own MCP server at `/api/mcp` registers the same four tools, and
the chat reaches them through MCP instead.
