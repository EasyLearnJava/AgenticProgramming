# Weather Chatbot (Nimbus)

> **Status:** step 1 of the [plan](PLAN.md) is done: the project skeleton. The chat itself comes in the next steps.
> Live at https://weather-chatbot-hazel.vercel.app/.

Nimbus is a weather chatbot on Vercel. You'll ask about the weather in plain words and see every tool call it makes,
through four lanes: REST or MCP, with or without auth. Today it has the chat page's hello card, a left menu, and
documentation for each finished build step.

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
| `components/` | The React components: the left menu, the Markdown viewer |
| `lib/` | The settings (`config.ts`, the only reader of environment variables) and the documentation's list and reader (`docs/`) |
| `docs/` | The documentation pages, one Markdown file per step |
| `tests/` | The unit tests (`unit/`) and a stand-in they need (`stubs/`) |
| `PLAN.md` | The plan for the whole build |
| Settings files | `package.json` (scripts, exact versions), `tsconfig.json`, `biome.json`, `vitest.config.ts`, `next.config.ts`, `.npmrc`, `.gitignore`, `.gitattributes` |

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

(A `Network:` line with your machine's address is left out.) Open http://localhost:3000: the hello card, with the menu
on the left and `Build: local` at its foot. `npm run build`, then `npm run start`, serves the production build instead.

## Test it

```bash
npm run lint        # Biome: formatting, and the naming and coding rules; a warning fails it too
npm run typecheck   # Next.js's route types, then TypeScript in strict mode
npm test            # the unit tests, with Vitest
npm run build       # the production build
```

```text
$ npm run lint
Checked 20 files in 1238ms. No fixes applied.

$ npm run typecheck
Generating route types...
✓ Types generated successfully

$ npm test
 Test Files  3 passed (3)
      Tests  7 passed (7)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Running next.config.ts took 233ms
  Creating an optimized production build ...
✓ Compiled successfully in 4.5s
  Running TypeScript ...
  Finished TypeScript in 724ms ...
  Collecting page data using 6 workers ...
  Generating static pages using 6 workers (0/5) ...
✓ Generating static pages using 6 workers (5/5) in 1085ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /docs
└   /docs/[slug]
  └ ● /docs/step-1

○  (Static)  prerendered as static content
●  (SSG)     prerendered as static HTML (uses generateStaticParams)
```

npm also prints each script's name and command first, and Vitest a start time and duration; those are left out here.
The times change from run to run. GitHub runs the same four checks on every push that touches this folder.

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

Step 2 in [PLAN.md](PLAN.md): the chat page, drawn from sample messages, with its tool chips, weather card, lane picker
and compare view.
