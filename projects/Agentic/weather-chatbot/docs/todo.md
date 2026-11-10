# To Do

What's still open in the Python rebuild, and why.

## Waiting on you

Everything only you can do, in your own accounts, has its own page: [Waiting on you](waiting-on-you.md).

## Done

- **Optional Qdrant weather answer cache:** exact lookup followed by hosted MiniLM similarity, with independent
  browser/context/date/unit guards, authenticated history and original evidence expiry. Complete successful weather
  answers can be reused for at most 120 seconds. [Weather cache](/weather-cache) shows private labels and freshness;
  Activity distinguishes cache reuse from model answers. Local mode is `on` after live provider and chat checks;
  hosted release remains separate. [Local evidence](technical-details.md#local-validation-on-9-november-2026)

- **Optional Mem0 travel preferences:** explicit preview and save of five typed defaults, browser-scoped ownership,
  edit/pause/resume/forget controls, provider readback verification and integration with chat and park planning.
  Stored values do not approve searches or replace fresh evidence. Hosted configuration and validation remain below.
  [How preferences work](technical-details.md#follow-an-approved-preference)

- **Repeated live evaluation and visitor feedback (step 19).** The harness keeps all three trials and reports both
  first-try and all-three scores. Visitors can share a category and answer reference in Activity. Reviewers can
  promote human-written park intake regressions. [The Evaluation Harness](step-19.md)

- **The Framework Preset is FastAPI** (2026-10-30), with no command overrides: step 1's deploy built with it.
- **LangSmith's variables** are set in Vercel (2026-10-30): `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`,
  `LANGSMITH_PROJECT`, `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS`. Step 3 is the first to use them.
- **Axiom's and Sentry's variables** are set in Vercel (checked 2026-10-31): `AXIOM_TOKEN`, `AXIOM_DATASET` and
  `SENTRY_DSN`. The live app's start line says Axiom, Sentry and LangSmith's tracing are on, and Axiom has its lines.
- **The Observability pages' query token** is set in Vercel (2026-11-02): `AXIOM_QUERY_TOKEN`, an advanced token
  that can only query `weather-chatbot`, with an expiry of a year at most and hourly and daily cost caps, as you
  set it. After the redeploy, each page and each of Activity's filters read the live dataset ([step 14](step-14.md)'s
  Deploy it). Renew it before it expires ([Waiting on you](waiting-on-you.md), part 6).
- **The TypeScript backup tag is deleted** (2026-10-31, step 13): it pointed at `c7165ac`, which `main`'s history
  keeps; this would make it again, annotated as it was:

  ```bash
  git tag -a weather-chatbot-typescript-backup c7165ac -m "Backup of the TypeScript weather chatbot (Nimbus) \
  before the Python rewrite; delete once the rewrite is complete."
  ```

## Next

- **Answer-cache release evidence:** preserve separate results for mock-provider regressions, real hosted embedding
  smoke cases and independent held-out cases. Check false hits, positive recall, provider errors, browser isolation,
  expiry, changed context and normal fallback on the exact preview before enabling reuse. Required hosted settings
  and the rollout sequence are on [Waiting on you](waiting-on-you.md#qdrant-weather-answer-cache).

- **Preference-memory release evidence:** validate the configured preview's save, reload, override, browser isolation,
  pause/resume and deletion flow, plus ordinary chat when memory is unavailable. Record the exact build and results
  before production. Required account settings and the stable signing secret are on
  [Waiting on you](waiting-on-you.md#mem0-travel-preferences). Expiry is not a substitute for verified deletion.

- **Step 18 travel release checks:** verify both providers on the intended preview and run the repeated chat
  evaluation. Record the tested commit, deployment, tool outcomes and timeouts before enabling production.
  [Step 18](step-18.md#deploy-it) describes the checks and [Waiting on you](waiting-on-you.md) covers settings.

- **Steps 16 and 17 release gate, checked 4 November 2026:** production NPS configuration, all three notice pages,
  RAG browsing/retrieval and explicit NPS chat checks were verified on `5de2c5c`. Completion tags remain withheld:
  the live `too-far-ahead` and `park-ambiguous-destination` goldens failed their tool-use rules (issues 125 and 126).
  Model timeouts were recorded separately and passed once rechecked. Correct the completed failures and repeat
  live validation on the intended tag commit. Public caches and request gates are per instance; monitor NPS quota.
  Preview configuration remains on [Waiting on you](waiting-on-you.md#3-vercels-environment-variables).

- **Park guidance, step 16:** review source changes before publishing a new index and rerun the retrieval benchmark.
  Qdrant native BM25 and hosted MiniLM now share one text/vector collection and the same ranker.
  Compare BM25, semantic-only and fused evidence with `tools.eval_park_hybrid`, including ranking quality and
  abstention. A provider fallback must not pass as a working hybrid setup. Validate the clean Linux/Vercel bundle,
  `/api/` edge rate limit, Playground trace and live answer goldens on the exact preview build. Hosted settings
  are on [Waiting on you](waiting-on-you.md#qdrant-hybrid-park-retrieval).

- **Hybrid park search, the review's leftovers (issue 182):** keep one Qdrant connection and remember an index's
  readiness for a while, instead of a new connection and a readiness call on every search; give the planner's
  searches a place in their own request's trace; make the hybrid comparison fail on any single case that got worse,
  not only on totals. Local MiniLM inference was removed by the Qdrant-only migration.

- **Park answers, after the first judged run (issue 183):** grow the 11 cases toward 30 to 50 per guide, in the words
  visitors use; record how often the judge agreed with your own reading; and recheck the reference answers when a
  stored page changes.

The rebuild is complete (step 13); these could come after it.

- **The cache's own errors as our warning (issues 60 and 72):** on Vercel, the runtime gives each request its cache,
  through the request's context, with the package's own `on_error`, which prints; an app can't give it one of its own.
  Open until the vercel package lets it.
- **certifi 2026.10.19, from 4 November, and pyasn1 0.6.5, from 11 November (issue 94):** a cutoff at midnight two
  weeks back takes each from that day on, not before: certifi's was uploaded at 02:24 UTC on 20 October, pyasn1's
  at 06:32 UTC on 27 October. certifi's puts back the emSign roots that weren't affected, as its advisory asks: move
  its cutoff in `exclude-newer-package` to `2026-10-21T00:00:00Z`, and the audit's `--exclude-newer` in CI with it.
  pyasn1's fixes 0.6.4's four slow decodings of ASN.1: give it a cutoff of its own, `2026-10-28T00:00:00Z`, then
  take its four `--ignore-vuln` out of CI's audit.
- **Why our MCP server's health check fails (issue 95):** one run in three failed, and step 15's Activity shows
  which check: all 23 of this app's failures were "Our MCP server (McpLaneError)", in well under a second, the
  other three checks working. Find why its call to our own server fails, and fix it.
- **A question's MCP calls in its timeline (issue 104):** on the MCP lanes, a tool runs in our MCP server's own
  request, so the question's timeline lacks its fetches. Our MCP lane could send the question's id in a header,
  which the server logs as `parentRequestId` only from our own calls (the bypass secret says so), and the
  timeline's query could ask for both.
- **A limit of its own for `/api/mcp`:** our MCP server needs no key, so within the firewall's 20 a minute one address
  could make 28,800 calls a day, past Open-Meteo's free 10,000; a lower rule for it, or a key, would hold them, and
  the lanes' own calls, carrying the bypass, would still pass.
