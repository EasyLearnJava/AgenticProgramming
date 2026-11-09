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
| `LANGSMITH_WORKSPACE_ID` = the workspace UUID that owns the tracing project, if the LangSmith key reaches more than one workspace | Activity's trace view reads each trace in that workspace; without it such a key's reads can fail, and the server log's `langsmith.read_failed` line names the lookup stage and LangSmith's status. A value that isn't a UUID stops the app at start, chat included, so paste it from LangSmith's workspace settings | Activity traces |
| `NPS_API_KEY`: Production done on 4 November 2026; configure Preview before preview validation | Production was configured as sensitive and the same source commit redeployed; local `.env.local` does not configure other Vercel environments | 17 |

For step 18, choose the providers for Preview under the same project settings. Set `FLIGHTS_ENABLED=true`
and/or `HOTELS_ENABLED=true`, keep `PARKS_ENABLED=true` for the planner, and redeploy that preview.
Both travel switches default to false. Review the preview's provider and repeated chat checks before choosing
the production flags. [Step 18](step-18.md#deploy-it)

Axiom's and Sentry's own variables are set already: the live app's start line said so (step 12's Deploy it).

**Production verified on 4 November 2026:** all three park pages returned complete notice checks, and explicit
NPS chat checks passed, with one model-timeout recheck. Deployment and release-gate evidence is in
[Step 17](step-17.md#deploy-it); two completed golden failures still prevent completion tags.

For another target, select the intended environment before saving the NPS key as a secret (Sensitive in dashboards
using that label). Include Preview for the preview you will validate, and Production for the production release. A new
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

## Step 19 preview evidence and production approval

1. Create an immutable Vercel Preview from the candidate commit. Set the preview’s Gemini and NPS credentials
   and the park, flight and hotel switches required by the live scenarios. Check the preview’s `/api/build`
   for its full commit and deployment ID. The Actions runner must be able to reach the preview through HTTPS.
   If its access policy blocks the runner, configure authorized preview access before running the evaluation.
2. Set the GitHub Actions repository variable `NIMBUS_HARNESS_PREVIEW_URL` to that preview origin.
   The nightly workflow uses it for smoke trials. To collect full evidence, dispatch **Weather chatbot** for
   the candidate revision with its `release_deployment` ID. Review the `nimbus-preview` artifact and job summary.
3. Decide who may release. GitHub’s required reviewer protection applies to jobs that reference the configured
   environment. Public repositories can use required reviewers on GitHub Free. For a future promotion job,
   configure a protected `production` environment, select the reviewer and prevent self-review. The current
   workflow produces evidence. An operator makes the final promotion decision. [GitHub deployment rules][gh-env]
4. Configure Vercel’s production branch and domain assignment to honor that decision. Preview-to-production
   promotion rebuilds with production settings. Record the production deployment ID and smoke-test it before
   tagging. If the operator needs to release a pretested production build, Vercel also supports disabling
   automatic domain assignment and promoting a staged production deployment. [Vercel deployment promotion][vc-promo]

[gh-env]: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
[vc-promo]: https://vercel.com/docs/deployments/promoting-a-deployment

## Mem0 travel preferences

Local `.env.local` settings do not configure Vercel. Before enabling this feature on a hosted target, add the following
in **Settings → Environment Variables** for that environment, then create a new deployment or redeploy:

| Setting | Value to supply | Purpose |
| --- | --- | --- |
| `MEMORY_ENABLED` | `true` only on the environment where you want preference memory | The feature defaults to off. |
| `MEM0_API_KEY` | Your Mem0 API credential, stored as a secret | Server-side read, save and delete access for approved preference profiles. Never place it in `.env.example`, a URL or a screenshot. |
| `MEMORY_COOKIE_SECRET` | A cryptographically random secret of at least 32 characters | Signs browser ownership and form tokens. Keep the same value across replicas and redeploys of this environment. |

Use a distinct signing secret for each environment and retain it securely. Changing it invalidates existing browser
links; those visitors can lose access to stored profiles and the ability to delete them through Nimbus. Do not rotate
it as part of an ordinary redeploy. Configure the Mem0 project and account usage limits appropriate for the target.

Validate the exact preview build before enabling production: save a synthetic DFW/Celsius/USD profile, reload it,
check a trip with an explicit different origin, and verify pause, resume and confirmed deletion. Use a separate browser
profile to check that it starts without those preferences. Confirm ordinary weather and park requests still work when
memory is disabled or unavailable. Record the tested commit, deployment and outcomes; local mock tests are not proof
that hosted credentials work.

For Mem0 tracing, use the existing LangSmith project, tracing key and both input/output-hiding settings; no new key
is required. After deploying the tracing change, check the synthetic save, read and delete in **Activity → Memory**,
open each Mem0 trace and confirm its timing and outcome. A chat that reads preferences should show both its Mem0
read link and, if the agent runs, its chat trace link. Confirm LangSmith contains no preference values, browser or
record identifiers, cookies or keys. Old memory events without trace IDs cannot acquire links retrospectively.

The feature offers browser-scoped preference memory, not accounts or a backup of conversation history. Expiry stops
normal use after 180 days from saving; it does not prove physical deletion. Review the controls and retention notice on
[My preferences](/preferences), and delete the synthetic profile after validation. Implementation details and failure
behavior are in [Technical details](technical-details.md#follow-an-approved-preference).

## Qdrant weather answer cache

Local setup created and verified the dedicated `nimbus_weather_cache` collection on the Free cluster. The key is in
ignored `.env.local`. Local mode is now `on` after real provider and chat checks, including a paraphrase answered
without Gemini or fresh tool calls. These settings do not configure Vercel; no hosted cache deployment was checked.
Before enabling the hosted feature, use **Project → Settings → Environment Variables** for the intended environment:

| Setting | Where the value comes from | Value for reuse |
| --- | --- | --- |
| `QDRANT_URL` | Qdrant Cloud → cluster → Overview → Endpoint | The HTTPS cluster endpoint, without a dashboard path. |
| `QDRANT_API_KEY` | The Database API key saved privately during cluster setup | Store as a secret; never put it in `.env.example`, chat, a URL or a screenshot. |
| `SEMANTIC_CACHE_MODE` | An operator-selected rollout mode | `shadow` for observation, then `on` after the release checks; `off` disables cache calls. |

The optional `QDRANT_COLLECTION` defaults to `nimbus_weather_cache`; `SEMANTIC_CACHE_THRESHOLD` defaults to `0.80`.
Use a dedicated collection per environment when separating preview and production data. A runtime key can be scoped
to the existing collection with read/write permission; setup requires a credential that can manage collections.
No separate embedding API key, Gemini embedding purchase or local model installation is required.

Create a deployment after changing settings. On that exact preview, ask “Dallas weather,” then “weather in Dallas”
in the same conversation. In `shadow` mode Gemini should still answer. With `on`, an accepted fresh repeat should
show a cache badge and no newly executed weather tools or Gemini call. Open [Weather cache](/weather-cache) to see
the label, source age and expiry. A separate browser profile must see no entries belonging to the first browser.
Verify changed units, dates, destinations, preferences and altered history reject reuse; verify expiry and provider
outages return to the normal flow. Park guidance, alerts, travel planning and Mem0 controls must retain their behavior.

Record the commit, deployment, mode, threshold and live evaluation artifacts before production. Keep provider errors
separate from semantic misses. A small successful smoke run does not establish held-out recall or production readiness.
The offline and live commands are in [Technical details](technical-details.md#configure-and-validate-answer-reuse).

The free cluster and hosted MiniLM option are enough for this bounded demo; no paid upgrade is selected by the app.
Review Qdrant's current Free limits and inactivity policy before relying on it for an unattended deployment.
Logical expiry prevents reuse immediately, while physical cleanup is opportunistic during later stores.
[Qdrant Free cluster documentation](https://qdrant.tech/documentation/cloud/create-cluster/).
