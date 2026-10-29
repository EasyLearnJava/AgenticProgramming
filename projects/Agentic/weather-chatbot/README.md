# Weather Chatbot (Nimbus)

> **Status:** steps 1 and 2 of the [plan](PLAN.md) are done: the project skeleton, and the chat page drawn from a
> sample conversation. The live chat comes in step 3. Live at https://weather-chatbot-hazel.vercel.app/.

Nimbus is a weather chatbot on Vercel. You'll ask about the weather in plain words and see every tool call it makes,
through four lanes: REST or MCP, with or without auth. Today the chat page shows a sample conversation whose tool chips
open to show each call's request, for whichever lane you pick, beside a left menu and documentation for each finished
build step.

**In one line:** a visit → Vercel serves pages Next.js built ahead of time → `app/layout.tsx` puts the left menu
beside the page → the chat page (`app/page.tsx`) or a documentation page (`app/docs/`).

## Documentation

The app explains itself: open **Documentation** in its left menu, or read the same pages in [`docs/`](docs/). There's
one page per build step: what it built, how it works, and how to check it.

## Before you start

- Node.js 22: the version Vercel runs this project on (`engines` in `package.json`)
- npm

## How it's organised

| Folder or file | What's in it |
|---|---|
| `app/` | The pages: the chat (`page.tsx`), the documentation (`docs/`), the 404 page (`not-found.tsx`), the shell around them (`layout.tsx`), and every style (`globals.css`) |
| `components/` | The React components: the left menu, the Markdown viewer, and the chat's parts (the chat window, the lane picker, a message, a tool chip, the weather card, the input, the compare view) |
| `lib/` | The settings (`config.ts`, the only reader of environment variables), the shared types, constants and helpers (`types.ts`, `constants.ts`, `utils.ts`), the sample conversation (`chat/`), and the documentation's list and reader (`docs/`) |
| `docs/` | The documentation pages, one Markdown file per step |
| `tests/` | The unit tests (`unit/`), the end-to-end tests in a real browser (`e2e/`), and a stand-in the unit tests need (`stubs/`) |
| `PLAN.md` | The plan for the whole build |
| Settings files | `package.json` (scripts, exact versions), `tsconfig.json`, `biome.json`, `vitest.config.ts`, `playwright.config.ts`, `next.config.ts`, `.npmrc`, `.gitignore`, `.gitattributes` |

CI lives at the repository's root, in `.github/workflows/weather-chatbot.yml`.

## Run it

From the repo's root:

```bash
cd projects/Agentic/weather-chatbot
npm install
npm run dev
```

```text
▲ Next.js 16.4.3 (Turbopack)
- Local:         http://localhost:3000
✓ Ready in 578ms
✓ Running next.config.ts took 54ms
```

(A `Network:` line with your machine's address is left out.) Open http://localhost:3000: the chat card with the
sample conversation, the menu on the left and `Build: local` at its foot. `npm run build`, then `npm run start`, serves
the production build instead.

## Test it

```bash
npm run lint        # Biome: formatting, and the naming and coding rules; a warning fails it too
npm run typecheck   # Next.js's route types, then TypeScript in strict mode
npm test            # the unit tests, with Vitest
npm run build       # the production build
npm run e2e         # the end-to-end tests: Playwright, in a real browser, on a desktop and a phone screen
```

```text
$ npm run lint
Checked 37 files in 305ms. No fixes applied.

$ npm run typecheck
Generating route types...
✓ Types generated successfully

$ npm test
 Test Files  6 passed (6)
      Tests  18 passed (18)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Running next.config.ts took 34ms
  Creating an optimized production build ...
✓ Compiled successfully in 462ms
  Running TypeScript ...
  Finished TypeScript in 436ms ...
  Collecting page data using 6 workers ...
  Generating static pages using 6 workers (0/6) ...
✓ Generating static pages using 6 workers (6/6) in 806ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /docs
└   /docs/[slug]
  ├ ● /docs/step-1
  └ ● /docs/step-2

○  (Static)  prerendered as static content
●  (SSG)     prerendered as static HTML (uses generateStaticParams)

$ npm run e2e
  20 passed (8.9s)
```

npm also prints each script's name and command first, Vitest a start time and duration, and Playwright one line per
test; those are left out here. The times change from run to run. `npm run e2e` serves the build that `npm run build`
made and tests it in Playwright's Chromium (install it once: `npx playwright install chromium`; or set
`E2E_BROWSER_CHANNEL=msedge` to use an installed Edge). With `BASE_URL` set (for example
`https://weather-chatbot-hazel.vercel.app`) it tests that site instead. GitHub runs all five on every push that
touches this folder.

## Deploy it on Vercel

1. In Vercel, choose **Add New → Project** and import the GitHub repository `EasyLearnJava/AgenticProgramming`.
2. Set **Root Directory** to `projects/Agentic/weather-chatbot`. Vercel detects Next.js; keep the default build
   settings.
3. Choose **Deploy**. The Node.js version comes from `package.json` (`22.x`).
4. In the project's settings, set **Ignored Build Step** to `git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .`.
   Vercel runs it in the Root Directory: it exits with 0 (skip the build) only when nothing in this folder changed
   since the last successful deployment. On the first deployment the variable is empty, so `git` fails, and Vercel
   builds.

## Next

Step 3 in [PLAN.md](PLAN.md): `REST · no auth`, the first live lane: the four weather tools, Open-Meteo's API, and the
chat route with Gemini.
