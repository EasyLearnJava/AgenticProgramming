# AgenticProgramming

Agents built one step at a time, starting from the smallest LangChain chain and adding a model, memory, tools
and more along the way. Every step is its own project folder, with just the code.

| Step | Project | What it adds |
|---|---|---|
| 1 | [`projects/01-langchain-basic`](projects/01-langchain-basic) | The smallest LangChain chain (`PromptTemplate` → `RunnableLambda`), invoked once |
| 2 | [`projects/02-langchain-python`](projects/02-langchain-python) | The same chain in Python (`prompt \| to_text`), served by a FastAPI route |
| 3 | [`projects/03-langchain-button`](projects/03-langchain-button) | Nothing runs on load: each button click calls the server once |
| 4 | [`projects/04-langchain-input`](projects/04-langchain-input) | One input: a `{name}` in the template, sent as a JSON `POST`, checked by Pydantic (422 on a bad name) |
| 5 | [`projects/05-langchain-inputs`](projects/05-langchain-inputs) | Three inputs (greeting, name, city), a default with `prompt.partial()`, `Literal` choices and per-field errors |
| 6 | [`projects/06-langchain-parallel`](projects/06-langchain-parallel) | One input, several results: `RunnableParallel`, `RunnablePassthrough`, `.assign()` and the chain's graph |
| 7 | [`projects/07-langchain-branch`](projects/07-langchain-branch) | `RunnableBranch` picks a formal or casual path; `batch()` greets a list in one call, with `max_concurrency` |
| 8 | [`projects/08-vibecode-data-app`](projects/08-vibecode-data-app) | A Streamlit app over a fruit-sales CSV (filters, totals, two charts), built with an AI coding assistant, one mini-spec at a time |
| 9 | [`projects/09-gemini-key`](projects/09-gemini-key) | A Gemini API key, kept secret: loaded from `.env` with `python-dotenv`, checked at start-up, never sent to the page or committed |
| 10 | [`projects/10-gemini-llm`](projects/10-gemini-llm) | The first real LLM call: `prompt \| ChatGoogleGenerativeAI \| StrOutputParser`, Gemini writes the greeting; plain tests plus one live test |
| 11 | [`projects/11-gemini-tokens`](projects/11-gemini-tokens) | What each call costs: tokens counted before and after (`count_tokens`, `usage_metadata`), latency, price per call, and `max_output_tokens` cutting the answer off |
| 12 | [`projects/12-gemini-stream`](projects/12-gemini-stream) | Streaming: `chain.astream()` → FastAPI `StreamingResponse` → the page's `getReader()` loop, with the time to the first words |

## How the repo works

```text
AgenticProgramming/
└─ projects/                  one folder per step
   ├─ 01-langchain-basic/     JavaScript (Node)
   │  ├─ hello.js             the code
   │  ├─ package.json         its dependencies and `npm start`
   │  └─ README.md            what it shows and how to run it
   ├─ 02-langchain-python/    Python
   │  ├─ hello.py             the chain
   │  ├─ main.py              the FastAPI server
   │  ├─ index.html           the page that calls the server on load
   │  ├─ tests/               pytest tests
   │  ├─ requirements.txt     its dependencies
   │  └─ README.md
   ├─ 03-langchain-button/    Python, same files as 02; index.html calls the server on a button click
   ├─ 04-langchain-input/     Python, same files as 02; the page sends a name, main.py checks it
   ├─ 05-langchain-inputs/    Python, same files as 02; greeting, name and city, each checked on its own
   ├─ 06-langchain-parallel/  Python, same files as 02; one name in, four results out, plus the chain's graph
   ├─ 07-langchain-branch/    Python, same files as 02; two paths picked by the input, and a batch endpoint
   ├─ 08-vibecode-data-app/   Python with Streamlit: app.py (the page), data.py (pandas), fruit_sales.csv, tests/
   ├─ 09-gemini-key/          Python: config.py (loads and checks the key), main.py, index.html, .env.example, tests/
   ├─ 10-gemini-llm/          Python, same files as 02 plus config.py and .env.example; Gemini writes the answer
   ├─ 11-gemini-tokens/       Python, same files as 10; each answer comes with its tokens, time and cost
   └─ 12-gemini-stream/       Python, same files as 10; the answer streams to the page as Gemini writes it
```

From project 9 on, a project may need your Gemini API key. It goes in that project's `.env` file (copied from
`.env.example`) or in a Codespaces secret, never in git. See [project 9's README](projects/09-gemini-key/README.md).

Each project installs and runs on its own:

```bash
# JavaScript (from the repo root)
cd projects/01-langchain-basic
npm install
npm start
```

```bash
# Python (from the repo root): the same for every FastAPI project, 02 to 07 and 09 on
# (09 on also need your key in their .env first: see project 9)
cd projects/02-langchain-python
pip install -r requirements-dev.txt
python hello.py               # just the chain, in the terminal
uvicorn main:app --reload     # the server: open http://127.0.0.1:8000 for the page
```

```bash
# Streamlit (project 08)
cd projects/08-vibecode-data-app
pip install -r requirements-dev.txt
streamlit run app.py          # open http://localhost:8501
```

In GitHub Codespaces, open the server from the **Ports** tab (port 8000, or 8501 for Streamlit) instead of
`127.0.0.1`: `https://<codespace-name>-8000.app.github.dev`. See [project 2's README](projects/02-langchain-python/README.md).
Only one server can use port 8000 at a time: stop one project's server (Ctrl+C) before starting another.

## Adding the next step

1. Create `projects/NN-short-name/` with the next number.
2. Add the code, a `package.json` (or `requirements.txt` for Python) and a short `README.md`.
3. Add a row to the table above.
