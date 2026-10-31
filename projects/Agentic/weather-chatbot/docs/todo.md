# To Do

What's still open in the Python rebuild, and why. The TypeScript version's list is kept as
[To do_deprecated](todo_deprecated.md).

## Waiting on you

Everything only you can do, in your own accounts, has its own page: [Waiting on you](waiting-on-you.md).

## Done

- **The Framework Preset is FastAPI** (2026-10-30), with no command overrides: step 1's deploy built with it.
- **LangSmith's variables** are set in Vercel (2026-10-30): `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`,
  `LANGSMITH_PROJECT`, `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS`. Step 3 is the first to use them.

## Next

- **Step 13:** evals and release: golden questions as LangSmith datasets, a load test, rollback, the Technical
  details page.
- **Skip the deploys other projects' pushes start:** Vercel deploys Nimbus on every push to `main`, so its build
  label can name another project's commit (issue 21); an `ignoreCommand` in `vercel.json` would end the build when
  this folder hasn't changed.
- **When the rebuild is done (step 13):** delete the backup tag `weather-chatbot-typescript-backup`.
