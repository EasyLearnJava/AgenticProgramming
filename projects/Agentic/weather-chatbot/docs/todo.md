# To Do

What's still open in the Python rebuild, and why. The TypeScript version's list is kept as
[To do_deprecated](todo_deprecated.md).

## Waiting on you

Everything only you can do, in your own accounts, has its own page: [Waiting on you](waiting-on-you.md).

## Done

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

The rebuild is complete (step 13); these could come after it.

- **The cache's own errors as our warning (issues 60 and 72):** on Vercel, the runtime gives each request its cache,
  through the request's context, with the package's own `on_error`, which prints; an app can't give it one of its own.
  Open until the vercel package lets it.
- **Each golden asked three times (issue 92):** the storm question missed twice in ten asks, and a golden asked once
  can't show a rule that fails one time in five. Asking each three times and grading all three would show how often
  any golden misses.
- **Visitors' feedback:** a thumb on each answer, kept with its request id, would grade answers the golden questions
  never ask.
- **certifi 2026.10.19, from 4 November, and pyasn1 0.6.5, from 11 November (issue 94):** a cutoff at midnight two
  weeks back takes each from that day on, not before: certifi's was uploaded at 02:24 UTC on 20 October, pyasn1's
  at 06:32 UTC on 27 October. certifi's puts back the emSign roots that weren't affected, as its advisory asks: move
  its cutoff in `exclude-newer-package` to `2026-10-21T00:00:00Z`, and the audit's `--exclude-newer` in CI with it.
  pyasn1's fixes 0.6.4's four slow decodings of ASN.1: give it a cutoff of its own, `2026-10-28T00:00:00Z`, then
  take its four `--ignore-vuln` out of CI's audit.
- **Which health check fails (issue 95):** one run in three failed, and Activity says only "not answering". One
  query in Axiom, the `health.check` lines that are `down`, by `check` and `errorClass`, would say which; then
  Activity's health rows could name the lanes that were down, from each `health.done` line's `lanes`.
- **A limit of its own for `/api/mcp`:** our MCP server needs no key, so within the firewall's 20 a minute one address
  could make 28,800 calls a day, past Open-Meteo's free 10,000; a lower rule for it, or a key, would hold them, and
  the lanes' own calls, carrying the bypass, would still pass.
