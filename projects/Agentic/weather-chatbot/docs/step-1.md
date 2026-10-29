# Step 1 · The Project Skeleton

**What this step built:** the app's skeleton, set up the way every later step works: a Next.js app on Vercel, this
left menu and documentation, a build line that says which version is running, the code checks, and CI.

## What you see

- **The chat page** (Chat, in the menu): for now, a hello card in the chat's mint-and-teal design. The chat itself
  arrives in steps 2 and 3.
- **The left menu:** Chat, Documentation, and at the bottom the build that's running, for example
  `Build 1a2b3c4 · production`: the first 7 characters of the Git commit Vercel built. On a laptop it says
  `Build: local` (or `Build: development` after `vercel env pull`).
- **This documentation:** one page per finished step. Each page says what the step built, how it works, and how to check
  it yourself.

## How it works

### From a visit to the page

1. You open the site. Vercel sends HTML it **built ahead of time**: these pages are the same for every visitor, so
   Next.js renders them once, when Vercel builds the app. Next.js calls them static pages.
2. `app/layout.tsx` wraps every page: the `<html>` element, the left menu (`components/side-menu.tsx`), and the page
   itself beside it.
3. `app/page.tsx` is the chat page, and `app/docs/` holds these pages. The colours come from `app/globals.css`, whose
   tokens were read from the design image (PLAN.md, section 6).
4. The menu is the only component of ours that runs in the browser (it starts with `"use client"`): it needs to know
   which page you're on, to highlight it. Next.js also adds its small router script to every page, so moving between
   pages doesn't reload them.

### Where this documentation comes from

- Each page is a Markdown file in `docs/` (this one is `docs/step-1.md`), so it reads the same on GitHub.
- `lib/docs/doc-list.ts` lists the pages: each one's address, step, title and summary.
- `app/docs/[slug]/page.tsx` turns each Markdown file into HTML while Vercel builds the app, with `react-markdown`. Raw
  HTML inside the Markdown is never rendered, and an address that isn't in the list is a 404.

### Which build is running

`lib/config.ts` is the only file that reads environment variables. When Vercel builds a deployment made from Git, it
sets `VERCEL_GIT_COMMIT_SHA` (the commit it's building) and `VERCEL_ENV` (`production` or `preview`); Zod checks both,
an empty value counts as missing, and the layout shows `Build <commit> · <environment>` at the foot of the menu.
Without a commit, the line only says where it runs: `Build: local` on a laptop (`Build: development` after
`vercel env pull`, which sets `VERCEL_ENV`). After every push, that line is how we
confirm the new version is live.

### How Vercel deploys it

1. A push to `main` on GitHub starts a deployment.
2. Vercel builds only this folder (the project's **Root Directory** is `projects/Agentic/weather-chatbot`), with
   Node.js 22 (`engines` in `package.json`).
3. If the project's **Ignored Build Step** is set as the README says
   (`git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- .`), Vercel compares this folder with its last successful
   deployment, and skips the build when nothing in it changed. The comparison covers every commit since then, not just
   the last one.
4. When the build passes, https://weather-chatbot-hazel.vercel.app/ serves the new version.

### The checks, and CI

| Command | What it checks |
|---|---|
| `npm run lint` | Biome: formatting, and the naming and coding rules (PLAN.md, sections 7.9 and 7.10); a warning fails it too |
| `npm run typecheck` | TypeScript 7 in strict mode, with Next.js's route types |
| `npm test` | The unit tests in `tests/unit/`, with Vitest |
| `npm run build` | The production build, as Vercel runs it |

GitHub runs the same four on every push that touches this folder, on any branch.
The workflow is `.github/workflows/weather-chatbot.yml`, at the repository's root, where GitHub looks for it; its runs
are under the repository's **Actions** tab.

Checked when this step was built: adding a file named `BadName.ts`, a function taking `any`, and a `console.log` made
`npm run lint` fail with `useFilenamingConvention`, `noExplicitAny` and `noConsole`; removing them made it pass again.

## Files in this step

| File | What it does |
|---|---|
| `app/layout.tsx` | The shell: the menu on the left, the page beside it, the build line |
| `app/page.tsx` | The chat page (a hello card, for now) |
| `app/docs/page.tsx` | The documentation's first page: the list of steps |
| `app/docs/[slug]/page.tsx` | One documentation page, from its Markdown file |
| `app/not-found.tsx` | The page for an address that doesn't exist |
| `app/globals.css` | The design tokens and every style |
| `components/side-menu.tsx` | The left menu |
| `components/markdown-doc.tsx` | Shows a Markdown document as HTML |
| `lib/config.ts` | The settings: the only reader of environment variables |
| `lib/docs/doc-list.ts` | The list of documentation pages |
| `lib/docs/read-doc.ts` | Reads a page's Markdown file |
| `docs/step-1.md` | This page |
| `tests/unit/config.test.ts`, `tests/unit/docs/doc-list.test.ts`, `tests/unit/docs/read-doc.test.ts` | The unit tests |
| `vitest.config.ts`, `tests/stubs/server-only.ts` | The unit tests' settings, and a stand-in they need |
| `next.config.ts`, `tsconfig.json`, `biome.json` | The Next.js, TypeScript and Biome settings |
| `package.json`, `package-lock.json`, `.npmrc` | The dependencies, at exact versions |
| `.gitignore`, `.gitattributes` | What Git ignores, and LF line endings on every OS |
| `.github/workflows/weather-chatbot.yml` | CI, at the repository's root |

## Check it yourself

From `projects/Agentic/weather-chatbot`, one command at a time:

```bash
npm install
npm run lint
npm run typecheck
npm test
npm run build
npm run dev
```

Then open http://localhost:3000: the menu says `Build: local`. On https://weather-chatbot-hazel.vercel.app/ it shows the
commit Vercel built.

## What's next

**Step 2:** the chat page, drawn from sample messages: the bubbles, the tool chips with their path labels, the weather
card, the four-lane picker and the compare view.
