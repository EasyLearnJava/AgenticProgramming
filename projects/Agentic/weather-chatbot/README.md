# Weather Chatbot (Nimbus)

> **Status:** step 1 of the [plan](PLAN.md): a hello page in the chat's design, so the project can be connected to
> Vercel. The chat itself comes in the next steps.

Nimbus is a weather chatbot on Vercel. You'll ask about the weather in plain words and see every tool call it makes,
through four lanes: REST or MCP, with or without auth. Today it's one page: a card in the mint-and-teal design, with a
hello message from the bot.

**In one line:** `npm run dev` → Next.js renders `app/page.tsx` inside `app/layout.tsx` → the hello card, styled by
`app/globals.css`.

## What you'll build

A Next.js 16 app with one static page, set up the way the rest of the build will be: TypeScript 7 in strict mode,
Biome for formatting and linting (the naming and coding rules in [PLAN.md](PLAN.md), sections 7.9 and 7.10), and
dependencies pinned to exact versions.

## Before you start

- Node.js 22: the version Vercel runs this project on (`engines` in `package.json`)
- npm

## Files

| File | What it is |
|---|---|
| `app/page.tsx` | The hello page: the chat card, with one message from the bot |
| `app/layout.tsx` | The shell around every page: its language, its title and the global styles |
| `app/globals.css` | The design tokens read from the shared image (PLAN.md, section 6), and the base styles |
| `next.config.ts` | Next.js settings: no `X-Powered-By` header, React's strict mode, no `AGENTS.md` written by `next dev` |
| `tsconfig.json` | TypeScript, strict, with the `@/` import alias |
| `biome.json` | Formatting and lint rules, naming included |
| `package.json`, `package-lock.json`, `.npmrc` | The dependencies, pinned to exact versions |
| `.gitignore` | Next.js's build output and the types it generates |
| `.gitattributes` | Keeps LF line endings on every OS, as Biome expects |
| `PLAN.md` | The plan for the whole build |

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

(A `Network:` line with your machine's address is left out.) Open http://localhost:3000 to see the mint page with the
hello card. `npm run dev` reloads the page as you edit;
`npm run build`, then `npm run start`, serves the production build instead.

## Test it

```bash
npm run lint        # Biome: formatting and lint rules, naming included
npm run typecheck   # Next.js's route types, then TypeScript in strict mode
npm run build       # the production build
```

```text
$ npm run lint
Checked 7 files in 1092ms. No fixes applied.

$ npm run typecheck
Generating route types...
✓ Types generated successfully

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Running next.config.ts took 89ms

  Creating an optimized production build ...
✓ Compiled successfully in 829ms
  Running TypeScript ...
  Finished TypeScript in 2.7s ...
  Collecting page data using 4 workers ...
  Generating static pages using 4 workers (0/3) ...
✓ Generating static pages using 4 workers (3/3) in 5.6s
  Finalizing page optimization ...

Route (app)
┌ ○ /
└ ○ /_not-found

○  (Static)  prerendered as static content
```

npm also prints each script's name and command first; that's left out here. The times change from run to run. There
are no tests yet: they start with the build (PLAN.md, section 10).

## Deploy it on Vercel

1. In Vercel, choose **Add New → Project** and import the GitHub repository `EasyLearnJava/AgenticProgramming`.
2. Set **Root Directory** to `projects/Agentic/weather-chatbot`. Vercel detects Next.js; keep the default build
   settings.
3. Choose **Deploy**. The Node.js version comes from `package.json` (`22.x`).
4. In the project's settings, set **Ignored Build Step** to `git diff HEAD^ HEAD --quiet -- .`, so commits elsewhere
   in the repo don't redeploy this project. The command runs in the Root Directory; when nothing changed there, it
   exits with 0, which skips the build.

## Next

[PLAN.md](PLAN.md): the rest of step 1 (tests and CI), then the chat page and the four lanes.
