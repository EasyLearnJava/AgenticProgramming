# AgenticProgramming

Agents built one step at a time, starting from the smallest LangChain chain and adding a model, memory, tools
and more along the way. Every step is its own project folder, with just the code.

| Step | Project | What it adds |
|---|---|---|
| 1 | [`projects/01-langchain-basic`](projects/01-langchain-basic) | The smallest LangChain chain (`PromptTemplate` → `RunnableLambda`), invoked once |

## How the repo works

```text
AgenticProgramming/
└─ projects/                  one folder per step
   └─ 01-langchain-basic/
      ├─ hello.js             the code
      ├─ package.json         its dependencies and `npm start`
      └─ README.md            what it shows and how to run it
```

Each project installs and runs on its own:

```bash
cd projects/01-langchain-basic
npm install
npm start
```

## Adding the next step

1. Create `projects/NN-short-name/` with the next number.
2. Add the code, a `package.json` (or `requirements.txt` for Python) and a short `README.md`.
3. Add a row to the table above.
