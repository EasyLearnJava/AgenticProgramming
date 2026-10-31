# To Do

What's still open in the Python rebuild, and why. The TypeScript version's list is kept as
[To do_deprecated](todo_deprecated.md).

## Waiting on you

| What | Why | Where |
|---|---|---|
| Delete `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` | They uploaded the TypeScript app's source maps; Python has none to upload, so nothing reads them now. `SENTRY_DSN` stays, for step 12 | Vercel, Settings, Environment Variables |
| Add `VERCEL_TELEMETRY_DISABLED` = `1` to the project's variables | Step 7 turns the vercel package's telemetry off in its code, before importing it (issue 58); a variable in Vercel's settings is in place even if Vercel's runtime imports the package first | Vercel, Settings, Environment Variables |
| The firewall's rules: a bypass for the app's own calls, then a rate limit on `/api/*` | Step 11: without it, one script can use up Gemini's free quota and Apify's credit for everyone | Vercel, the project's Firewall |

## Done

- **The Framework Preset is FastAPI** (2026-10-30), with no command overrides: step 1's deploy built with it.
- **LangSmith's variables** are set in Vercel (2026-10-30): `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`,
  `LANGSMITH_PROJECT`, `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS`. Step 3 is the first to use them.

## Next

- **Step 8:** our own MCP server, with FastMCP, at `/api/mcp`, offering the same four weather tools.
- **Step 12, the cache's own errors as our warning:** on Vercel, the package's store prints them and gives a miss
  (issue 60); built with an `on_error` that raises, each would be one `cache.failed` line, with the request's id.
- **Skip the deploys other projects' pushes start:** Vercel deploys Nimbus on every push to `main`, so its build
  label can name another project's commit (issue 21); an `ignoreCommand` in `vercel.json` would end the build when
  this folder hasn't changed.
- **When the rebuild is done (step 13):** delete the backup tag `weather-chatbot-typescript-backup`.
