# AgenticProgramming

Agents built one step at a time, starting from the smallest LangChain chain and adding a model, memory, tools
and more along the way. Every step is its own project folder, with just the code.

| Step | Project | What it adds |
|---|---|---|
| 1 | [`projects/01-langchain-basic`](projects/01-langchain-basic) | The smallest LangChain chain (`PromptTemplate` → `RunnableLambda`), invoked once |
| 2 | [`projects/02-langchain-python`](projects/02-langchain-python) | The same chain in Python (`prompt \| to_text`), served by a FastAPI route |

## How the repo works

```text
AgenticProgramming/
└─ projects/                  one folder per step
   ├─ 01-langchain-basic/     JavaScript (Node)
   │  ├─ hello.js             the code
   │  ├─ package.json         its dependencies and `npm start`
   │  └─ README.md            what it shows and how to run it
   └─ 02-langchain-python/    Python
      ├─ hello.py             the chain
      ├─ main.py              the FastAPI server
      ├─ index.html           the page that calls the server on load
      ├─ tests/               pytest tests
      ├─ requirements.txt     its dependencies
      └─ README.md
```

Each project installs and runs on its own:

```bash
# JavaScript (from the repo root)
cd projects/01-langchain-basic
npm install
npm start
```

```bash
# Python (from the repo root)
cd projects/02-langchain-python
pip install -r requirements-dev.txt
python hello.py               # just the chain, in the terminal
uvicorn main:app --reload     # the server: open http://127.0.0.1:8000 and the page calls it
```

In GitHub Codespaces, open the server from the **Ports** tab (port 8000) instead of `127.0.0.1`:
`https://<codespace-name>-8000.app.github.dev`. See [project 2's README](projects/02-langchain-python/README.md).

## Adding the next step

1. Create `projects/NN-short-name/` with the next number.
2. Add the code, a `package.json` (or `requirements.txt` for Python) and a short `README.md`.
3. Add a row to the table above.
