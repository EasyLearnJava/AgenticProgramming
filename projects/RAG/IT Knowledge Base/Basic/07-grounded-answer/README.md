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
- **All the code in one file**, `pipeline.py`: the loader, the splitter, the models, the embedding, the vector store,
  the retriever and the prompt, and `main()`, which names each step, then runs it. Two files are apart:
  `config.py`, which checks the key, and `utils.py`, which prints the answers

"Grounded" means the answer is meant to come from the knowledge base, not from what the model learned in training.
The prompt asks for that; nothing here checks it.

**Try it:** `python pipeline.py`, and compare the two answers to a question only this knowledge base can answer.

---

## 🏗️ Architecture

```text
pipeline.py: main(), the one file to run: it holds the steps below, and calls each in order:
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
│  make_retriever(store)       │  ← embeds the question (1 call), finds the 5 closest chunks: found
│    .invoke(question)         │
│  prompt.format_messages()    │  ← the 5 chunks and the question in one prompt: messages
│  chat.invoke(messages)       │  ← chat = model | StrOutputParser(): Gemini's answer (1 call)
└──────────────┬───────────────┘
               │ found, messages, answer
               ↓
      print_answer(), in utils.py: the prompt as Gemini got it (messages),
                                   the answer, then the articles of the chunks found
               │
  question ────┤ for comparison, with no retriever and no articles
               ↓
      chat.invoke(question): Gemini alone (1 call); print_answer_alone() prints it
```

### The Pipeline in This Project

1. **Run** → `python pipeline.py`: `main()` runs each step in order, and prints each one's name
2. **Load** → `load_documents()` reads the 10 articles: their text and their labels
3. **Chunk** → `split_documents()` cuts them into 28 chunks of at most 512 characters
4. **Embed** → `embed_chunks()` embeds the 28 chunks in one call to Gemini
5. **Store** → `store_vectors()` stores them in Qdrant, each with its vector
6. **Retrieve** → `found = make_retriever(store).invoke(question)`: the retriever embeds the question (one call)
   and finds the 5 closest chunks
7. **Prompt** → `format_docs()` numbers the chunks and titles them, and `prompt.format_messages()` puts them into the
   prompt with the question: `messages`
8. **Answer** → `gemini-3.5-flash-lite` writes the answer from `messages` (one call), and `StrOutputParser` turns it
   into plain text
9. **Print** → `print_answer()`, from `utils.py`: the question, the prompt as Gemini got it, the answer, then the
   articles the chunks came from, each once
10. **Compare** → the same question goes to Gemini alone (one call), and `print_answer_alone()` prints its answer

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, made in the Google Cloud console, under APIs & Services > Credentials. There, under API
  restrictions, restrict it to the Gemini API (the Generative Language API; not Gemini for Google Cloud API, a
  different service), so a leaked key can't be used for anything else. Every call to Gemini uses your key's quota

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

It creates this folder's `.venv` the first time, installs `requirements-dev.txt` into it, then runs `python
pipeline.py` in this folder with the venv's Python, so there's nothing to activate. The project's output is the same
as in Step 5, after run.py's own lines saying what it creates, installs and runs. A question at the end of the command
goes to `pipeline.py`.

---

## 🧪 Testing

```bash
python -m pytest -m "not live"       # 35 passed, 7 deselected  (add -v for one line per test)
```

The plain tests use stand-ins for Gemini (`KeywordEmbeddings` for the embeddings, LangChain's `FakeListChatModel`
for the answers), so they need no key and make no calls. They check:

- **The prompt**: it holds the rules and the articles, then the question; and the model gets the chunks found as the
  articles
- **The printing**: what `print_answer()` prints, the prompt as Gemini got it too, and what `print_answer_alone()`
  prints
- **The pipeline**: it embeds the chunks, then the question, once each, and prints the steps, the prompt, the answer,
  the sources and the answer alone; the prompt it prints is exactly what the model got, and the model alone gets only
  the question; it takes a question of your own; and no other file runs anything

The 7 deselected tests are live tests, marked `live`: they call the real Gemini, so they need your key in `.env`;
with no key, `tests/conftest.py` skips them, so plain `python -m pytest` runs only the others. One live test asks how
to bake bread: the answer must say the knowledge base doesn't cover it ("cover") and have no "flour" or "yeast" (no
recipe from what Gemini knows). Together they embed 118 texts, more than the free tier's limit of 100 a minute, so on
the free tier, run them in two goes, a minute apart: `python -m pytest -m live -k "vpn_question or off_topic"` (the
two answers from the chunks, 30 texts), then `python -m pytest -m live -k "not vpn_question and not off_topic"`
(the other five, 88).

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
...
```

That's what retrieval adds: knowledge the model never saw. Here Gemini alone says it doesn't know; a model can also
make up a confident answer instead (a hallucination).

### 2. The Prompt, Exactly as Gemini Got It

```python
("system", "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles "
           "below. If they don't cover the question, say that the knowledge base doesn't cover it. ..."),
("human", "{question}"),
```

The system message holds the rules and the articles (`{context}`); the human message holds the question. The run
fills in the prompt with `prompt.format_messages()`, then hands Gemini those very messages and prints them, so what
you read is what Gemini got. For the Building C question, the articles start:

```text
Articles:
[1] WiFi Connectivity Issues Office
Notes: Building C has older access points scheduled for upgrade Q2. Capacity issues during all-hands meetings.

[2] WiFi Connectivity Issues Office
```

The search put the one chunk with the answer first. The other 4 are there too: the prompt always gets 5 of the 28
chunks, and some are about something else (a printer, a Salesforce role). The 10 articles, 6,621 characters in all,
would fit whole in the prompt, but many real knowledge bases don't: a model reads only so much at once (its context
window), and sending all of it would cost more tokens with every question (a token is a piece of a word, about 4
characters of English). Answers are counted in tokens too: `MAX_OUTPUT_TOKENS`, in `pipeline.py`, caps each one at
500.

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
the chunks the search found, and a search always finds 5 chunks, here from 5 different articles (for the Building C
question, from 3). And Gemini alone, asked the same question, wrote a bread recipe, until it reached
`MAX_OUTPUT_TOKENS`, 500.

### 4. Retrieve, Then Answer, One Step at a Time

```python
found = make_retriever(store).invoke(question)                    # the 5 closest chunks (1 call)
messages = prompt.format_messages(context=format_docs(found), question=question)
answer = chat.invoke(messages)                                    # Gemini's answer from them (1 call)
```

Step 5 runs one step at a time, as 06 does, and gives each result a name: `found`, the chunks the search found;
`messages`, the prompt filled in with them and the question; `answer`, Gemini's reply. Gemini gets `messages` itself,
so the prompt the run prints is exactly what Gemini got, and `print_answer()` lists the articles of `found` as the
sources.

### 5. Runnables Joined With `|`

```python
chat = model | StrOutputParser()
chat.invoke(messages)   # with the articles: the prompt, filled in
chat.invoke(question)   # alone: just the question, no prompt, so no articles
```

The chat model and the parser are both Runnables, and `|` joins them into one: the model's reply goes to the parser,
which turns it into plain text, and one `invoke()` runs both. The same `chat` gives both answers; only what it's
given changes.

### 6. One File Runs the Steps

`pipeline.py` is the only file that runs anything: `main()` runs Steps 1 to 4, printing a line each, then Step 5,
the search and the answer, which `print_answer()`, from `utils.py`, prints with the prompt; then the question alone,
which `print_answer_alone()` prints. `config.py` and `utils.py` only define what it uses, and building the models
makes no call, so importing any of them makes no call. The question and the two models are parameters of `main()`,
so the tests pass stand-ins for Gemini.

### 7. The Code in One File, the Helpers Apart

```python
from config import MissingKeyError, load_api_key     # checks the key, before the models are built
from utils import print_answer, print_answer_alone   # helpers: showing the two answers
```

`pipeline.py` holds the project's code, top to bottom: the settings (the data file, the column lists, the chunk size
and overlap, the two models' names and settings, the collection's name, `TOP_K`, the sample questions and
`QUESTION`), the loader, the splitter, the two models, `embed_chunks()`, the vector store (`make_vector_store()` and
`store_vectors()`), the retriever (`make_retriever()` and `format_docs()`), the prompt, then
`main()`, which runs them. Two files stay apart. `utils.py` holds `print_answer()` and `print_answer_alone()`, which
print what `main()` hands them, so `utils.py` needs nothing from `pipeline.py`. `config.py` holds the key check,
because the tests need it before `pipeline.py` is imported: `tests/conftest.py` asks it whether there's a real key,
and gives the models a fake one when there isn't.

---

## 🛠️ Troubleshooting

**Issue**: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
**Fix**: Windows PowerShell blocks scripts until you allow them. Allow local ones once, with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or for this window only, with
`Set-ExecutionPolicy -Scope Process Bypass`, then activate again (Step 2). The one command needs no activating.

**Issue**: `GoogleGenerativeAIError: Error embedding content (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.', ...`
**Fix**: Gemini didn't accept the key in `.env`. Copy it again from the Google Cloud console, with nothing before or
after it.

**Issue**: An error with `403 PERMISSION_DENIED` in it
**Fix**: Google refused the key for this service. In the Google Cloud console, open the key: under API restrictions
it should list the Gemini API (the Generative Language API), not Gemini for Google Cloud API, and under
Application restrictions, None. New settings can take up to 5 minutes to work.

**Issue**: `GoogleGenerativeAIError: Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, ...`
**Fix**: Your key has used its quota. On the free tier, that's 100 embedded texts a minute, and a run embeds 29; the
message ends with "Please retry in" and a number of seconds. Wait that long, then run it again.

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'` (or another of the packages)
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).`
**Fix**: There's no `.env` with a key in this folder. Do Step 4.

**Issue**: `Can't build the models: GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.`
**Fix**: `.env` still says `your-key-here`. Replace it with your key.

**Issue**: `Can't build the models: .env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.`
**Fix**: `.env` was saved in another encoding, often UTF-16 by Windows PowerShell 5's `echo ... > .env`. Save it
again as UTF-8, or make it with `copy .env.example .env` and edit it.

**Issue**: `python utils.py` or `python config.py` prints nothing
**Fix**: Those files only define what `pipeline.py` uses. Run `python pipeline.py` (Step 5), which runs every step.

---

## 💡 Ideas to Try

- Ask how long a Salesforce role change takes to work: `python pipeline.py "how long until my new Salesforce role
  works?"`. The SaaS article says up to 30 minutes. Does Gemini alone guess?
- In `pipeline.py`, cut both rules from the prompt: "using only the knowledge base articles below" and "If they don't
  cover the question, say that the knowledge base doesn't cover it." Then ask the bread question again. In one run,
  Gemini still declined, in its own words: "I'm sorry, but I can only assist with IT-related issues based on the
  available articles. For password resets, VPN, printing, database connections, or SaaS access, please let me know."
  Its answer points to what still kept it on topic: the prompt's first sentence, "You are an IT help-desk assistant",
  and the articles it was still given. Then ask an IT question no article covers, such as "my monitor flickers", with
  and without the rules. The label above the answer, "asked to use only the chunks found", is fixed text in
  `print_answer()`, whatever the prompt says. Tests check the prompt has both rules, and the live bread test looks for
  "cover", so put them back before you run the tests.
- Change `TOP_K` in `pipeline.py` from 5 to 1, and see how the prompt, the answer and the sources change. Tests check
  for 5, so put it back before you run the tests.
