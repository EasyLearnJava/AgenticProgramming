# Waiting on You

Everything only you can do: settings in your own accounts, which the app's code never changes and the build never
sees. Each says what to do, why, and where, step by step, with the step that needs it. Once one is done, it moves to
[To do](todo.md)'s Done list; one that has to be done again later stays here, marked done, with its steps.

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
| Add `NPS_API_KEY` as a server-side secret in each intended Preview and Production environment | Official park notices show "not configured" without it; the key in local `.env.local` does not configure Vercel | 17 |

Axiom's and Sentry's own variables are set already: the live app's start line said so (step 12's Deploy it).

For the NPS key, select the intended environment before saving it as a secret (Sensitive in dashboards using that
label). Include Preview for the preview you will validate, and Production for the production release. A new
deployment or redeploy is required after changing environment variables. Open `/parks/alerts`, choose each supported
park and run a check: results should show a fetch time or an explicit failure, rather than "not configured".
Activity distinguishes authentication failures, NPS outages and cached reports without displaying the key.
See Vercel's [environment variable guide](https://vercel.com/docs/environment-variables/managing-environment-variables).

## 4. Monitoring: a dashboard, alerts and an uptime monitor (step 12)

They live in your Axiom, Sentry and uptime accounts. Step 12's chapter has each query, ready to paste, under
"Dashboards and alerts, ready to set up".

1. **Axiom:** a dashboard named `Nimbus`, one chart per query; then the monitors, each emailing you.
2. **Sentry:** its default alert, a high-priority issue by email, is already on; add an issue alert on the tag
   `errorClass` equals `AuthError`, at most once a day: Apify refused the token.
3. **An uptime monitor**, on a free plan (UptimeRobot or Better Stack):
   `https://weather-chatbot-hazel.vercel.app/api/health` every 5 minutes, alerting on anything but `200`.

## 5. The golden questions in LangSmith, and a rollback, practised (step 13)

1. **The evals in LangSmith.** Put a LangSmith API key in `.env.local` on your computer, as `LANGSMITH_API_KEY`:
   from where you saved Vercel's, or a new one from LangSmith's settings (Vercel won't show a Sensitive variable
   again). Then, from the project's folder:
   `uv run python -m tools.evals https://weather-chatbot-hazel.vercel.app --langsmith`. The golden questions become
   the dataset `nimbus-golden`, and the run an experiment named for the build; each later run adds one beside it.
   Without the key, the tool says so before it asks anything.
2. **A rollback, once.** In Vercel, roll production back to the deployment before the current one, as step 13's
   chapter says; check the site; then undo the rollback, so new pushes go live again.

## 6. Axiom: a token that can only query, for the Observability pages (step 14)

**Done on 2 November 2026:** the live pages read Axiom ([To do](todo.md)'s Done list). The steps stay here for when
the token expires, a year at most: make a new one the same way, and change the variable.

Activity, Performance, Evaluations and Health's history read the app's lines back from Axiom. Until this is set, each
says "This deployment can't read Axiom yet", and Health still shows the checks now; once the token has expired, each
says Axiom didn't answer. The token the app already has can only ingest, and stays as it is.

1. **The token.** In Axiom, **Settings → API tokens → New API token**, an **advanced** one: dataset access to
   `weather-chatbot` only, with **query** and nothing else; an expiry, a year at most; and, if your plan offers them,
   an hourly and a daily cap on its query cost. Size the caps on the pages' 11 queries: each copy of the app runs each
   at most once a minute, while someone opens its page, and Vercel may run a few copies at once; a cap that's reached
   makes every page say Axiom didn't answer until it resets. Copy the token once: Axiom won't show it again. A
   personal token won't do: Axiom's edge takes API tokens only.
2. **The variable.** In Vercel, the project's **Settings → Environment Variables**: `AXIOM_QUERY_TOKEN`, for
   Production, **Sensitive**. Then **Deployments**, the latest production one, **Redeploy**: a deployment keeps the
   variables it was built with.
3. **Check it.** Open https://weather-chatbot-hazel.vercel.app/performance: numbers, not the notice. The app's start
   line in Vercel's logs says `"axiomQuery": true`. When the token expires, the pages say Axiom didn't answer, and
   Sentry hears of it once on each copy of the app: make a new one, and change the variable.
