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
          ↓
┌──────────────────────────────┐
│  Qdrant, in memory           │  ← Step 3, store.add_documents(): the 28 chunks, embedded by Gemini (1 call)
└──────────────┬───────────────┘
               │
  question ────┤ Step 4: Retrieve and answer
               ↓
┌──────────────────────────────┐
│  make_rag_chain()            │
│  ├─ docs: the retriever      │  ← embeds the question (1 call), finds the 5 closest chunks
│  ├─ question: passed through │
│  └─ answer: prompt → Gemini  │  ← the 5 chunks and the question in one prompt (1 call)
└──────────────┬───────────────┘
               │ {"docs", "question", "answer"}
               ↓
      print_answer(): the answer, then its sources
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Load** → `load_documents()` reads the 10 articles: their text and their labels
3. **Chunk** → `split_documents()` cuts them into 28 chunks of at most 512 characters
4. **Embed and store** → `store.add_documents()` embeds the chunks in one call to Gemini and stores them in Qdrant
5. **Retrieve** → the retriever embeds the question (one call) and finds the 5 closest chunks
6. **Prompt** → `format_docs()` numbers the chunks and titles them; they go into the prompt with the question
7. **Answer** → `gemini-3.5-flash-lite` writes the answer (one call), and `StrOutputParser` turns it into plain text
8. **Print** → `print_answer()`: the question, the answer, then the articles the chunks came from, each once

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

It prints Steps 1 to 3 in one line each, then Step 4 in full: the question, Gemini's answer, then the articles the
chunks came from, each once. The parts in `< >` come from Gemini, so they change from run to run:

```text
Step 1: Read the knowledge base: 10 documents
Step 2: Chunk: 28 chunks of at most 512 characters
Step 3: Embed and store: 28 points, in Qdrant in memory
Step 4: Retrieve and answer
Question: How do I fix VPN connection timeouts?

Answer (Gemini's, from the chunks found):
<Gemini's answer>

Sources (the articles of the chunks found, closest first):
  <article title>
  ...
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

## 📁 Project Structure

```text
07-grounded-answer/
├── pipeline.py                           # the one file to run: main() calls each step in order
├── rag_chain.py                          # the prompt, make_rag_chain() and print_answer(): Step 4
├── retriever.py                          # make_retriever() (5 chunks per question), format_docs()
├── vector_store.py                       # make_vector_store(): Qdrant, in memory
├── models.py                             # the Gemini models: the embedding model and the chat model
├── config.py                             # load_api_key(): the key from .env, checked before anything else
├── chunking.py                           # split_documents(): chunks of at most 512 characters
├── knowledge_base.py                     # load_documents(): the 10 articles as Documents
├── data/
│   └── sample_it_kb.csv                  # the knowledge base: 10 IT support articles
├── tests/
│   ├── conftest.py                       # skips the live tests when there's no key
│   ├── fakes.py                          # stand-ins for Gemini, so the plain tests make no calls
│   └── test_*.py                         # one test file per module
├── .env.example                          # copy it to .env and put your key in it
├── requirements.txt                      # the packages, pinned to exact versions
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # finds the tests in tests/, and defines the "live" marker
└── README.md                             # you are here
```

---

## 🧪 Testing

```bash
python -m pytest                     # 31 passed, 5 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini (`KeywordEmbeddings` for the embeddings, LangChain's `FakeListChatModel`
for the answers), so they need no key and make no calls. For the chain, they check that the prompt holds the rules
and the articles, then the question; that the chain gives back the chunks, the question and the answer; that the
model gets the chunks it found as the articles; and what `print_answer()` prints. For the pipeline, they check that
it embeds the chunks, then the question, once each, and prints the steps, the answer and its sources; that it takes
a question of your own; and that no other file runs anything.

The 5 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too. To run only the plain ones: `python -m pytest -m "not live"`.

---

## 📊 Understanding the Output

After one line each for Steps 1 to 3, and `Step 4: Retrieve and answer`, the output is:

```text
Question: How do I fix VPN connection timeouts?          ← the question: the default, or the one you gave

Answer (Gemini's, from the chunks found):                ← Gemini's words, written from the 5 chunks only
<Gemini's answer>

Sources (the articles of the chunks found, closest first):
  <article title>                                        ← each article once, even when 2 of its chunks were found
  ...
```

The chain gives back one dictionary: `{"docs": [the 5 chunks], "question": "...", "answer": "..."}`. The answer is
printed from `"answer"`, and the sources from the titles in `"docs"`.

Each run makes 3 calls to Gemini: the chunks' embeddings, the question's embedding, and the answer.

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

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 3, printing a line each, then Step 4,
the chain, and `print_answer()` prints its result. The other files only define the steps, so importing them makes no
call. The question and the two models are parameters of `main()`, so the tests pass stand-ins for Gemini.

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

## 📚 Next Steps

**[08 · RAG Engine](../08-rag-engine/README.md)**: this project answers one question per run, from a chain built for
it. 08 puts the whole pipeline in one class: built once, then answering each question with up to 3 sources.

**[Advanced · 07 · Grounded Answer](../../Advanced/07-grounded-answer/README.md)** (planned): the same project,
production grade. Its README lists what it will add.

### Ideas to Try

- Ask something the knowledge base doesn't cover, like `python pipeline.py "how do I bake bread"`, and see whether
  the answer says the knowledge base doesn't cover it, as the prompt's rules ask.
- Remove "using only the knowledge base articles below" from the prompt, ask the same question, and compare the
  answers.
- Change `TOP_K` in `retriever.py` from 5 to 1, and see how the answer and its sources change.
