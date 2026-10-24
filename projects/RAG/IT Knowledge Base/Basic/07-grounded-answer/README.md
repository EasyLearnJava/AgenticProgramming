# 07 · Grounded Answer

Answer a question from the IT knowledge base: find the 5 chunks closest to the question, put them and the question
into one prompt, and ask Gemini to answer from those chunks only, naming the articles it used. That's RAG: retrieval
first, then generation. Then ask Gemini the same question alone, with no articles, to see what retrieval adds. Built
with **LangChain**, **Gemini** (`gemini-embedding-001` and `gemini-3.5-flash-lite`) and **Qdrant**, running in memory.

> **Needs:** Python 3.11 or newer, and a Gemini API key. Each run makes 4 calls to Gemini: 2 embed 29 texts (the 28
> chunks and the question), and 2 write answers (with the articles, then without).

---

## 🎯 What This Project Does

- **Gets the knowledge base ready**: reads the 10 articles, cuts them into 28 chunks, embeds them with Gemini and
  stores them in Qdrant, in memory
- **Finds the 5 chunks closest to the question** with a retriever
- **Puts them into one prompt** with the question: its rules ask Gemini to answer using only these articles, and to
  say so when they don't cover the question
- **Prints the prompt exactly as Gemini got it**: the rules, the 5 numbered chunks, then the question
- **Has Gemini write the answer** with its chat model, `gemini-3.5-flash-lite`
- **Lists the articles of the chunks found**, closest first: what the search found, not a checked list of what the
  answer used
- **Asks Gemini the same question alone**, with no articles, for comparison
- **Runs from one file**, `pipeline.py`, which names each step, then runs it

"Grounded" means the answer is meant to come from the knowledge base, not from what the model learned in training.
The prompt asks for that; nothing here checks it.

**Try it:** `python pipeline.py`, and compare the two answers to a question only this knowledge base can answer.

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
      print_answer(), in utils.py: the prompt as Gemini got it (prompt.format_messages()),
                                   the answer, then the articles of the chunks found
               │
  question ────┤ for comparison, with no retriever and no articles
               ↓
      model | StrOutputParser(): Gemini alone (1 call); print_answer_alone() prints it
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
9. **Print** → `print_answer()`, from `utils.py`: the question, the prompt as Gemini got it, the answer, then the
   articles the chunks came from, each once
10. **Compare** → the same question goes to Gemini alone (one call), and `print_answer_alone()` prints its answer

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Generative Language API, so a leaked key can't be used for anything else. Every
  call to Gemini uses your key's quota

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
python pipeline.py                   # "When will the access points in Building C be upgraded?", both ways
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
python -m pytest                     # 37 passed, 7 skipped     (add -v for one line per test)
```

The plain tests use stand-ins for Gemini (`KeywordEmbeddings` for the embeddings, LangChain's `FakeListChatModel`
for the answers), so they need no key and make no calls. They check:

- **The chain**: the prompt holds the rules and the articles, then the question; the chain gives back the chunks, the
  question and the answer; and the model gets the chunks it found as the articles
- **The printing**: what `print_answer()` prints, the prompt as Gemini got it too, and what `print_answer_alone()`
  prints
- **The pipeline**: it embeds the chunks, then the question, once each, and prints the steps, the prompt, the answer,
  its sources and the answer alone; the prompt it prints is exactly what the model got, and the model alone gets only
  the question; it takes a question of your own; and no other file runs anything

The 7 skipped tests are live tests, marked `live`: they call the real Gemini, so `tests/conftest.py` skips them when
no key is set. With your key in `.env`, they run too, and one checks that an off-topic question gets "the knowledge
base doesn't cover it". Together they embed more than 100 texts, the free tier's limit for a minute, so there run
the plain ones with `python -m pytest -m "not live"`, and the live ones one file at a time, a minute apart:
`python -m pytest -m live tests/test_rag_chain.py`.

---

## 🎓 Key Concepts Demonstrated

### 1. RAG: Retrieval First, Then Generation

First the retriever finds the chunks that match the question; then the model writes the answer with those chunks in
its prompt. A model knows only what it learned in training, and nothing about this help desk. The run asks a question
only this knowledge base can answer, both ways. With the articles:

```text
Answer (Gemini's, asked to use only the chunks found):
Based on the knowledge base, the access points in Building C are scheduled for upgrade in Q2 (due to older access points and capacity issues during all-hands meetings).

Articles used: [1] WiFi Connectivity Issues Office
```

Alone, with no articles:

```text
For comparison, the same question to Gemini alone, with no articles:
I do not have access to real-time schedules, internal IT tickets, or company calendars, so I cannot tell you when the access points in Building C will be upgraded.
```

That's what retrieval adds: knowledge the model never saw. Here Gemini alone says it doesn't know; a model can also
make up a confident answer instead.

### 2. The Prompt, Exactly as Gemini Got It

```python
("system", "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles "
           "below. If they don't cover the question, say that the knowledge base doesn't cover it. ..."),
("human", "{question}"),
```

The system message holds the rules and the articles (`{context}`); the human message holds the question. The run
prints the prompt filled in, with `prompt.format_messages()`, the chain's own template, so what you read is what
Gemini got. For the Building C question, the articles start:

```text
Articles:
[1] WiFi Connectivity Issues Office
Notes: Building C has older access points scheduled for upgrade Q2. Capacity issues during all-hands meetings.

[2] WiFi Connectivity Issues Office
```

The search put the one chunk with the answer first. The other 4 are there too: the prompt always gets 5, and some
are about something else (a printer, a Salesforce role).

### 3. Asked, Not Guaranteed

"Using only the knowledge base articles below" asks Gemini to stay with the articles; it can't make it. Models mostly
do as asked, but nothing in this project checks the answer against the chunks: RAG makes made-up answers rarer, not
impossible. For `python pipeline.py "how do I bake bread"`, Gemini followed the rule:

```text
Answer (Gemini's, asked to use only the chunks found):
The knowledge base doesn't cover it.

Sources (the articles of the chunks found, closest first):
  Database Connection Timeout
  Password Reset Failed
  VPN Connection Timeout
  Printer Not Found
  SaaS Access Permission Denied
```

Two things to see. The sources still list 5 articles, though the answer used none of them: they're the articles of
the chunks the search found, and a search always finds 5. And Gemini alone, asked the same question, wrote a bread
recipe, until it reached `MAX_OUTPUT_TOKENS`, 500.

### 4. One Chain That Keeps the Chunks

```python
RunnableParallel(docs=retriever, question=RunnablePassthrough()).assign(answer=answer)
```

`RunnableParallel` runs the retriever on the question and passes the question through, side by side. `.assign()`
then adds the answer. Because `"docs"` stays in the result, `print_answer()` can show which articles the answer
came from.

### 5. Runnables Joined With `|`

```python
answer = (lambda x: {"context": format_docs(x["docs"]), "question": x["question"]}) | prompt | model | StrOutputParser()
model | StrOutputParser()   # the question alone: no retriever, no prompt, so no articles
```

Each part is a Runnable, and `|` passes one part's output to the next: the chunks become one text for the prompt, the
prompt goes to the model, and the parser turns the model's reply into plain text. One `invoke()` runs it all.

### 6. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 4, printing a line each, then Step 5,
the chain, and `print_answer()`, from `utils.py`, prints its result with the prompt; then the question alone, which
`print_answer_alone()` prints. The other files only define the steps and that
helper, so importing them makes no call. The question and the two models are parameters of `main()`, so the tests
pass stand-ins for Gemini.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: `GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.', ...`
**Fix**: Gemini didn't accept the key in `.env`. Copy it again from the Google Cloud console, with nothing before or
after it, and check it's restricted to the Generative Language API, not to another one.

**Issue**: `GoogleGenerativeAIError: Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, ...`
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute, and a run embeds 29; the
message ends with "Please retry in" and a number of seconds. Wait that long, then run it again.

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

- Ask how long a Salesforce role change takes to work: `python pipeline.py "how long until my new Salesforce role
  works?"`. The SaaS article says up to 30 minutes. Does Gemini alone guess?
- Remove "using only the knowledge base articles below" from the prompt, ask the bread question again, and compare
  the answers.
- Change `TOP_K` in `retriever.py` from 5 to 1, and see how the prompt, the answer and its sources change. Tests
  check for 5, so put it back before `python -m pytest`.
