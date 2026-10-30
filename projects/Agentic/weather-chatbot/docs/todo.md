# To Do

What's still open in the Python rebuild, and why. The TypeScript version's list is kept as
[To do_deprecated](todo_deprecated.md).

## Waiting on you

| What | Why | Where |
|---|---|---|
| Switch the project's Framework Preset from Next.js to FastAPI, with no Build, Install or Output command overrides | Vercel builds the app as it finds it: with the Next.js preset, the Python app's build fails, and the TypeScript app keeps serving | Vercel, the project's Settings, Build and Deployment |
| Delete `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` | They uploaded the TypeScript app's source maps; Python has none to upload, so nothing reads them now. `SENTRY_DSN` stays, for step 12 | Vercel, Settings, Environment Variables |
| LangSmith: `LANGSMITH_API_KEY` (Sensitive), `LANGSMITH_TRACING=true`, `LANGSMITH_PROJECT=weather-chatbot`, `LANGSMITH_HIDE_INPUTS=true`, `LANGSMITH_HIDE_OUTPUTS=true` | Step 4 traces each run of the agent, with visitors' questions and answers hidden from LangSmith | smith.langchain.com for the key; then Vercel, Settings, Environment Variables |
| Neon Postgres, from Vercel's Marketplace | Step 6 keeps each chat on the server, and step 7 caches Open-Meteo's answers there; Neon sets `DATABASE_URL` for the project | Vercel, the project's Storage tab |
| The firewall's rules: a bypass for the app's own calls, then a rate limit on `/api/*` | Step 11: without it, one script can use up Gemini's free quota and Apify's credit for everyone | Vercel, the project's Firewall |

## Next

- **Step 2:** the chat streams a fixed answer over server-sent events with HTMX, with Stop and our own error
  sentences, before any AI.
- **When the rebuild is done (step 13):** delete the backup tag `weather-chatbot-typescript-backup`.
