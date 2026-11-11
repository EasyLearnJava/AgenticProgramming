# RivalScope

RivalScope helps product managers research three competitors in a local web app. It uses Tavily and Nebius to replace manual searching and comparison, pauses for shortlist and briefing approval, and gives reviewers a sourced report they can export. The evaluation target is a usable briefing within five minutes for at least eight of ten representative live research tasks.

## Run on Windows

Open PowerShell in the RivalScope directory. Use Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open [RivalScope on localhost](http://127.0.0.1:8501). Select **Trello demo** and click **Find competitors**. Confirm the shortlist, inspect the evidence, and approve the briefing to download Markdown and CSV. Demo mode uses a fixed set of public sources and works without keys.

## Enable live research

1. Sign in to the [Tavily dashboard](https://app.tavily.com/) and copy an API key.
2. Sign in to [Nebius Token Factory](https://tokenfactory.nebius.com/), create an inference API key, and check that your account can use a model with JSON mode. See the [Nebius quickstart](https://docs.tokenfactory.nebius.com/quickstart) and [JSON mode guide](https://docs.tokenfactory.nebius.com/ai-models-inference/json).
3. In the RivalScope directory, create a local configuration file.

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

4. Paste your keys after `TAVILY_API_KEY=` and `NEBIUS_API_KEY=`. Keep `NEBIUS_MODEL=openai/gpt-oss-120b` or enter the exact ID of a JSON mode model available to your account. Keep `RIVALSCOPE_MODE=demo` to open on the demo, or set it to `live`.
5. Open the app and select **Live research**. Try `Trello`, website `trello.com`, and market focus `US work management for small teams`. An environment variable of the same name takes precedence over the value in `.env`.

Keep `.env` local. The example file contains no keys. Search and inference use your provider accounts and may consume credits.

## Project structure

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit entry point and navigation |
| `rivalscope/ui.py`, `pages/documentation.py` | Research workspace, reviews, and Documentation page |
| `rivalscope/workflow.py` | LangGraph routing, approval checkpoints, and the gap loop |
| `rivalscope/session.py` | SQLite checkpointer and run controls |
| `rivalscope/agents.py`, `prompts.py` | Discovery, gathering, extraction, and evidence checks |
| `rivalscope/providers.py` | Tavily and Nebius HTTP adapters |
| `rivalscope/models.py`, `reports.py` | Data contracts and exports |
| `rivalscope/demo.py` | Frozen public-source Trello dataset |
| `docs/` | User guide, project write-up, and recording script |
| `examples/` | Approved sample briefing in Markdown and CSV |
| `tests/` | Workflow, provider, and Streamlit checks |

The app includes a [user guide](docs/USER_GUIDE.md). The [project write-up](docs/PROJECT_WRITEUP.md) is ready to paste into a submission Google Doc. See the [demo script](docs/DEMO_SCRIPT.md) and [sample briefing](examples/trello-briefing.md).

## Verify locally

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use temporary databases and mocked provider responses. No API keys are required.
