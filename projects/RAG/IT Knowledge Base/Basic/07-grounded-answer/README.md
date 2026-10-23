# 07 · Grounded Answer

Answer a question from the IT knowledge base: find the 5 chunks closest to the question, put them and the question
into one prompt, and let Gemini write the answer from those chunks only, with the articles they came from. That's
RAG: retrieval first, then generation. Built with **LangChain**, **Gemini** (`gemini-embedding-001` and
`gemini-3.5-flash-lite`) and **Qdrant**, running in memory.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Each run makes 3 calls to Gemini.

---

## 🎯 What This Project Does

- **Gets the knowledge base ready**: reads the 10 articles, cuts them into 28 chunks, embeds them with Gemini and
  stores them in Qdrant, in memory
- **Finds the 5 chunks closest to the question** with a retriever
- **Puts them into one prompt** with the question: its rules tell Gemini to answer using only these articles, and to
  say so when they don't cover the question
- **Has Gemini write the answer** with its chat model, `gemini-3.5-flash-lite`
- **Keeps the chunks it found**, so the answer comes with its sources: the articles the chunks came from
- **Runs from one file**, `pipeline.py`, which names each step, then runs it

"Grounded" means the answer comes from the knowledge base, not from what the model learned in training.

**Try it:** `python pipeline.py "my printer is missing"`, and read the answer and the articles it came from.

---

## 🏗️ Architecture

```text
pipeline.py: main(), the one file to run, calls each step in order:
data/sample_it_kb.csv                 10 articles
          │ Steps 1 and 2: load_documents(), split_documents()
          │ Step 3: embed_chunks(): the 28 chunks, embedded by Gemini (1 call)
          ↓
┌──────────────────────────────┐
│  Qdrant, in memory           │  ← Step 4, store_vectors(): 28 points, each chunk with its vector
└──────────────┬───────────────┘
               │
  question ────┤ Step 5: Retrieve and answer
               ↓
┌──────────────────────────────┐
│  make_rag_chain()            │
│  ├─ docs: the retriever      │  ← embeds the question (1 call), finds the 5 closest chunks
│  ├─ question: passed through │
│  └─ answer: prompt → Gemini  │  ← the 5 chunks and the question in one prompt (1 call)
└──────────────┬───────────────┘
               │ {"docs", "question", "answer"}
               ↓
      print_answer(), in utils.py: the answer, then its sources
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Load** → `load_documents()` reads the 10 articles: their text and their labels
3. **Chunk** → `split_documents()` cuts them into 28 chunks of at most 512 characters
4. **Embed** → `embed_chunks()` embeds the 28 chunks in one call to Gemini
5. **Store** → `store_vectors()` stores them in Qdrant, each with its vector
6. **Retrieve** → the retriever embeds the question (one call) and finds the 5 closest chunks
7. **Prompt** → `format_docs()` numbers the chunks and titles them; they go into the prompt with the question
8. **Answer** → `gemini-3.5-flash-lite` writes the answer (one call), and `StrOutputParser` turns it into plain text
9. **Print** → `print_answer()`, from `utils.py`: the question, the answer, then the articles the chunks came from,
   each once

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**: every call to Gemini uses your key's quota

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Basic/07-grounded-answer"   # from the repo root; quotes for the spaces
```

### Step 2: Create and Activate a Virtual Environment

```bash
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
```

Creating the venv is once only; activate it again in every new terminal.

### Step 3: Install Dependencies

```bash
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
```

### Step 4: Add Your Gemini Key

```bash
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
```

Open `.env` in an editor and put your key after `GOOGLE_API_KEY=`. You make a key in the Google Cloud console, under
APIs & Services > Credentials, as `.env.example` says. `.env` is in `.gitignore`, so your key never goes into git.

### Step 5: Run It

```bash
python pipeline.py
```

To ask your own question, put it after `pipeline.py`:

```bash
python pipeline.py "my printer is missing"
```

### Or: Run It in One Command

With your key in `.env` (Step 4), this one command does Steps 2, 3 and 5 for you:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/07-grounded-answer   # from the repo root
```

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs
`python pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The output is the same as
in Step 5. A question at the end of the command goes to `pipeline.py`.

---

## 🧪 Testing

```bash
python -m pytest                     # 35 passed, 6 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini (`KeywordEmbeddings` for the embeddings, LangChain's `FakeListChatModel`
for the answers), so they need no key and make no calls. For the chain, they check that the prompt holds the rules
and the articles, then the question; that the chain gives back the chunks, the question and the answer; that the
model gets the chunks it found as the articles; and what `print_answer()` prints. For the pipeline, they check that
it embeds the chunks, then the question, once each, and prints the steps, the answer and its sources; that it takes
a question of your own; and that no other file runs anything.

The 6 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 🎓 Key Concepts Demonstrated

### 1. RAG: Retrieval First, Then Generation

The model doesn't answer from memory. First the retriever finds the chunks that match the question; then the model
writes the answer from those chunks. What the model knows about this help desk is only what the chunks say.

### 2. A Prompt That Keeps the Answer Grounded

```python
("system", "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles "
           "below. If they don't cover the question, say that the knowledge base doesn't cover it. ..."),
("human", "{question}"),
```

The system message holds the rules and the articles (`{context}`); the human message holds the question. "Using only
the knowledge base articles below" is what keeps the answer grounded: without it, the model answers from what it
learned in training.

### 3. One Chain That Keeps the Chunks

```python
RunnableParallel(docs=retriever, question=RunnablePassthrough()).assign(answer=answer)
```

`RunnableParallel` runs the retriever on the question and passes the question through, side by side. `.assign()`
then adds the answer. Because `"docs"` stays in the result, `print_answer()` can show which articles the answer
came from.

### 4. Runnables Joined With `|`

```python
answer = (lambda x: {"context": format_docs(x["docs"]), "question": x["question"]}) | prompt | model | StrOutputParser()
```

Each part is a Runnable, and `|` passes one part's output to the next: the chunks become one text for the prompt, the
prompt goes to the model, and the parser turns the model's reply into plain text. One `invoke()` runs it all.

### 5. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 4, printing a line each, then Step 5,
the chain, and `print_answer()`, from `utils.py`, prints its result. The other files only define the steps and that
helper, so importing them makes no call. The question and the two models are parameters of `main()`, so the tests
pass stand-ins for Gemini.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `python rag_chain.py` prints nothing
**Fix**: That file only defines the step. Run `python pipeline.py` (Step 5), which runs every step.

---

## 💡 Ideas to Try

- Ask something the knowledge base doesn't cover, like `python pipeline.py "how do I bake bread"`, and see whether
  the answer says the knowledge base doesn't cover it, as the prompt's rules ask.
- Remove "using only the knowledge base articles below" from the prompt, ask the same question, and compare the
  answers.
- Change `TOP_K` in `retriever.py` from 5 to 1, and see how the answer and its sources change.
