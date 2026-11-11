## Run a competitor analysis

1. Choose **Trello demo** to try the workflow with the included public-source snapshot, or **Live research** to enter your own company. In Live mode, an official website and a market focus help resolve ambiguous names and define which competitors matter.
2. Click **Find competitors**. Review the proposed shortlist and its discovery sources. You can edit all three entries. If discovery is incomplete, fill the missing entries or use **Retry discovery** when offered.
3. Click **Confirm and research**. RivalScope looks for pricing, core features, positioning, and news for each competitor. The news window is 90 days through the research date.
4. Open each competitor to see the findings, source links, and supporting excerpts. **Company source** means the source URL matches the website on the reviewed shortlist. **External source** means the URL is on a different site. **No supported finding** means the workflow could not support a claim with the available evidence.
5. Approve the briefing to unlock Markdown and CSV. If fields are missing, **Retry missing evidence** offers one final pass before approval. **Discard briefing** ends the run.

The **Research activity** panel shows the work completed and any automatic follow-up. Save the research workspace URL with its run ID to reopen the same run after a browser or app restart.

## Set up the API keys

Get one key from the [Tavily dashboard](https://app.tavily.com/) and one from [Nebius Token Factory](https://tokenfactory.nebius.com/).

In PowerShell, from the RivalScope directory, run:

```powershell
Copy-Item .env.example .env
notepad .env
```

Paste each key after its corresponding equals sign:

```dotenv
RIVALSCOPE_MODE=demo
TAVILY_API_KEY=
NEBIUS_API_KEY=
NEBIUS_MODEL=openai/gpt-oss-120b
```

Use the exact model ID shown in the Nebius catalog for your account and check that the model supports JSON mode. Keep the file private. Back in the workspace, select **Live research**. Demo mode can be used without keys. [Nebius API key instructions](https://docs.tokenfactory.nebius.com/quickstart)

## What happens during a run

| Stage | What RivalScope does |
| --- | --- |
| Discovery | Searches Tavily for alternatives and overlap, then asks Nebius to shortlist up to three candidates supported by those results. |
| Shortlist review | Pauses until you confirm, edit, retry discovery, or discard. |
| Research | Runs a set of field-specific searches for each competitor. The first pricing search favors the reviewed company domain. |
| Analysis | Extracts structured findings and checks the source ID, field, and supporting quote. Pricing figures must appear in the quote. News requires a usable date in the research window. |
| Evidence check | Runs one automatic follow-up for the highest-priority missing field per eligible competitor. Earlier findings are kept. |
| Briefing compilation | Tallies covered fields and cited pages for the comparison and source review. |
| Briefing review | Shows the comparison and evidence. Export is enabled after approval. |

RivalScope stores run inputs, public search excerpts, decisions, and progress in `.rivalscope/runs.sqlite3` on this computer. API keys remain in the environment or local `.env` file. Discarded runs are marked in SQLite. The app runs on localhost and is designed for individual use.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Live mode asks for keys | Check the file is named `.env` and sits next to `app.py`. Enter values after the equals signs. |
| Provider refused access | Check the affected provider key, its account permissions, and available credits. |
| Nebius rejected the request | Check `NEBIUS_MODEL` against your account's catalog, including JSON mode support. |
| Discovery has fewer than three results | Add the missing competitors, narrow the scope in a new run, or retry discovery. |
| A field has no supported finding | Open the competitor’s research notes. You can request a final pass, leave the gap visible, or discard the briefing. |
| The workflow stopped unexpectedly | Reload the research workspace and use **Retry from checkpoint** if offered. |
