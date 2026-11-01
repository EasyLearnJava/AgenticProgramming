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
- **Skip the deploys other projects' pushes start:** Vercel deploys Nimbus on every push to `main`, so its build
  label can name another project's commit (issue 21); an `ignoreCommand` in `vercel.json` would end the build when
  this folder hasn't changed.
- **Visitors' feedback:** a thumb on each answer, kept with its request id, would grade answers the golden questions
  never ask.
- **Pin CI's actions by commit:** `actions/checkout@v7` and `astral-sh/setup-uv@v10.3.0` are pinned by tag, which
  their owners can move to other code; a commit's SHA can't move.
- **Scan the dependencies:** `pip-audit` in CI, or GitHub's Dependabot alerts, would flag a locked version with a
  known vulnerability; nothing does today.
- **A limit of its own for `/api/mcp`:** our MCP server needs no key, so within the firewall's 20 a minute one address
  could make 28,800 calls a day, past Open-Meteo's free 10,000; a lower rule for it, or a key, would hold them, and
  the lanes' own calls, carrying the bypass, would still pass.
