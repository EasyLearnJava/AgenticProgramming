# Waiting on You

Everything only you can do: settings in your own accounts, which the app's code never changes and the build never
sees. Each says what to do, why, and where, step by step, with the step that needs it. Once one is done, it moves to
[To do](todo.md)'s Done list.

## 1. Vercel's firewall: a bypass, then a rate limit (step 11)

Without it, one script can use up Gemini's free quota and Apify's credit for everyone. Step 11's live check found no
bypass secret in the deployment yet, so begin with the first part.

1. **The bypass secret.** In Vercel, the project's **Settings → Deployment Protection → Protection Bypass for
   Automation**: turn it on. Then **Deployments**, the latest production one, **Redeploy**: the secret reaches a
   deployment as `VERCEL_AUTOMATION_BYPASS_SECRET` only when it's built. The MCP lanes then send it with each call to
   our own MCP server, and each request a chip shows has it, masked.
2. **Our own calls.** The project's **Firewall → Configure → New Rule**, named "Our own calls": if **Request Header**
   `x-vercel-protection-bypass` **Equals** the secret from 1, then **Bypass**. Equals, never "is present": a rule on
   the header alone would let anyone skip the limit by sending one.
3. **The rate limit.** A second rule, below the first, named "Rate limit": if **Request Path Starts with** `/api/`,
   then **Rate Limit**: Fixed Window, 60 seconds, 20 requests, keyed by IP address, answering 429. Then **Review
   Changes → Publish**.
4. **Check it.** While a question runs on MCP · no auth, the Firewall's overview shows the bypass rule's matches
   growing. If you ever regenerate the secret, change rule 2 to match, and redeploy.

## 2. Apify: a monthly usage limit (step 10)

The lanes with auth cap their runs at 2 an answer and 25 a day, each run's charge at $0.01; a limit on Apify's side
caps the account itself, whatever happens to ours. In Apify's Console, **Billing → Limits**: set a monthly usage
limit, a few dollars at most.

## 3. Vercel's environment variables

In the project's **Settings → Environment Variables**, for Production, then a redeploy:

| What | Why | Step |
|---|---|---|
| Add `VERCEL_TELEMETRY_DISABLED` = `1` | The app turns the vercel package's telemetry off before any of its modules import it (issues 58 and 69); a variable is in place even if Vercel's runtime imports the package first | 7 |
| Delete `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` | They uploaded the TypeScript app's source maps; Python has none, so nothing reads them | 12 |

Axiom's and Sentry's own variables are set already: the live app's start line said so (step 12's Deploy it).

## 4. Monitoring: a dashboard, alerts and an uptime monitor (step 12)

They live in your Axiom, Sentry and uptime accounts. Step 12's chapter has each query, ready to paste, under
"Dashboards and alerts, ready to set up".

1. **Axiom:** a dashboard named `Nimbus`, one chart per query; then the monitors, each emailing you.
2. **Sentry:** its default alert, a high-priority issue by email, is already on; add an issue alert on the tag
   `errorClass` equals `AuthError`, at most once a day: Apify refused the token.
3. **An uptime monitor**, on a free plan (UptimeRobot or Better Stack):
   `https://weather-chatbot-hazel.vercel.app/api/health` every 5 minutes, alerting on anything but `200`.

## 5. The golden questions in LangSmith, and a rollback, practised (step 13)

1. **The evals in LangSmith.** Put `LANGSMITH_API_KEY`, the same key as Vercel's, in `.env.local` on your computer,
   then, from the project's folder:
   `uv run python -m tools.evals https://weather-chatbot-hazel.vercel.app --langsmith`. The golden questions become
   the dataset `nimbus-golden`, and the run an experiment named for the build; each later run adds one beside it.
   Without the key, the tool says so before it asks anything.
2. **A rollback, once.** In Vercel, roll production back to the deployment before the current one, as step 13's
   chapter says; check the site; then undo the rollback, so new pushes go live again.
