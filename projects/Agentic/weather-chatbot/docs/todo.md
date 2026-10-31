# To Do

What's still open in the Python rebuild, and why. The TypeScript version's list is kept as
[To do_deprecated](todo_deprecated.md).

## Waiting on you

| What | Why | Where |
|---|---|---|
| Delete `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` | They uploaded the TypeScript app's source maps; Python has none to upload, so nothing reads them now. `SENTRY_DSN` stays, for step 12 | Vercel, Settings, Environment Variables |
| The firewall's rules: a bypass for the app's own calls, then a rate limit on `/api/*` | Step 11: without it, one script can use up Gemini's free quota and Apify's credit for everyone | Vercel, the project's Firewall |

## Done

- **The Framework Preset is FastAPI** (2026-10-30), with no command overrides: step 1's deploy built with it.
- **LangSmith's variables** are set in Vercel (2026-10-30): `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`,
  `LANGSMITH_PROJECT`, `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS`. Step 4 is the first to use them.

## Next

- **Step 3:** Gemini's answer, through LangChain, streamed the same way: the system prompt, the model's input rules,
  and time limits on the call; and a cap on each answer, since on Vercel, Stop never reaches the function (issue 32).
- **Skip the deploys other projects' pushes start:** Vercel deploys Nimbus on every push to `main`, so its build
  label can name another project's commit (issue 21); an `ignoreCommand` in `vercel.json` would end the build when
  this folder hasn't changed.
- **When the rebuild is done (step 13):** delete the backup tag `weather-chatbot-typescript-backup`.
