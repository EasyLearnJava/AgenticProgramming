# IT Knowledge Base

An IT help-desk assistant that answers questions from a knowledge base of IT support articles, built with LangChain
and Gemini, one step at a time. You ask "How do I fix VPN connection timeouts?"; it finds the parts of the articles
that match, and Gemini is asked to write the answer from those parts only, naming the articles it used. That's RAG:
retrieval-augmented generation. A model needs RAG because it knows only what it learned in training, and nothing about
your own documents, such as these articles. To change what it knows, you change the articles, not the model: no
retraining or fine-tuning.

```text
once:          articles ─> chunks ─> embed them ─> store them in Qdrant
each question: question ─> embed it ─> find the closest chunks in Qdrant ─> prompt: the chunks + the question ─> Gemini ─> answer
                                                        │
                                                        └─> sources: the articles of the chunks found
```

It rebuilds the *IT Knowledge Base RAG Application* from the Pluralsight course *Integrating Knowledge Bases for
RAGs* ([its code](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2)), with LangChain in place of
LlamaIndex, Gemini in place of OpenAI, and a plain HTML page served by FastAPI in place of Next.js.

## The projects

The projects come in five levels:

- **`Entry/`**: the idea in three short Jupyter notebooks, before any of the app, with small models that run on the
  CPU, and Chroma. No API key.
- **`Basic/`**: the whole app, 01 to 10, one step at a time, each on the happy path: the data is assumed to be good.
- **`Intermediate/`**: the whole app built again as a production-grade codebase: one package per layer, each
  replaceable; every setting in `config.yaml`; errors that answer in one shape; and logs in which one trace ID follows
  each request through every layer, shown on the page under each answer. 01 is built.
- **`Advanced/`**: the same projects done again, production grade: each checks its input, handles what goes wrong,
  and reports it. 01 to 08 are built; 09 to 12 are planned, each with a README giving its plan, and
  [Advanced/README.md](Advanced/README.md) is the roadmap.
- **`Expert/`**: beyond one file: reading the knowledge base from many systems, in real time. 01 is planned, in
  [its TODO](Expert/01-read-the-knowledge-base/TODO.md); no code yet.

Each Basic folder, Intermediate/01 and each built Advanced folder is a project of its own: it holds the app as built so far plus one new piece, runs
on its own, and has its own tests. Projects 01 to 05 are the ingestion half (also called indexing): they get the
knowledge base ready to be searched (read, label, chunk, embed, store), once per run, with no question anywhere. 06
and 07 are the query half, which runs for each question: the user's question comes in at 06, and 07 onward answer it.
09 and 10 add the web app (an API, then a chat page): if you're here to learn RAG, you can skim them.

Beside them, [`RAG series/`](RAG%20series/README.md) will hold a notebook for each course of the Pluralsight path
*Retrieval Augmented Generation (RAG) for Developers*, each runnable in Google Colab; so far, course 1, Vector Space
Models and Embeddings in RAGs.

### Entry

| Project | What it does | Run it |
|---|---|---|
| `V1` | Four sentences embedded by `all-MiniLM-L6-v2` on the CPU and stored in Chroma, in memory; a question finds the 2 closest; then a keyword filter with re-ranking. Then inside the vectors: their numbers, their cosine similarities, and 2D and 3D graphs of them (PCA). Retrieval only: nothing writes an answer | In a Codespace: open `Entry/V1/rag_basics.ipynb`, then **Run All** |
| `V2` | Four longer documents stored twice, whole and cut into sentences ("windows"); the question searched whole, then reworded by hand and searched both ways | In a Codespace: open `Entry/V2/rag_basics.ipynb`, then **Run All** |
| `V3` | Eight one-line documents; `all-MiniLM-L6-v2` finds the 3 closest, a cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) scores each with the question and sorts them by that score, and precision@1 compares the two lists | In a Codespace: open `Entry/V3/rag_basics.ipynb`, then **Run All** |

### Basic

| Project | What it adds | Run it |
|---|---|---|
| `01-read-the-knowledge-base` | The CSV file of 10 articles read into LangChain `Document`s by a document loader | `python pipeline.py` |
| `02-documents-and-metadata` | Each article's text to search (title, problem, resolution, notes) kept apart from its labels (system, category, priority, tags) | `python pipeline.py` |
| `03-chunking` | The articles cut into chunks of at most 512 characters with `RecursiveCharacterTextSplitter`: 28 in all | `python pipeline.py` |
| `04-embeddings` | The 28 chunks turned into vectors by Gemini (`gemini-embedding-001`, 768 numbers each), in one call; then how close chunk 1 is to every other chunk. No question yet | `python pipeline.py` |
| `05-vector-store` | The chunks stored in Qdrant as points, written with Qdrant's `upsert()`: one per chunk, with its vector, text and labels, in memory, inside the script | `python pipeline.py` |
| `06-retriever` | The user's question: embedded, then searched in Qdrant for the 5 closest chunks; then both in one call with a retriever, a Runnable | `python pipeline.py` |
| `07-grounded-answer` | The RAG chain: the chunks and the question go into a prompt, and Gemini (`gemini-3.5-flash-lite`) is asked to answer from them only; then the same question without them | `python pipeline.py` |
| `08-rag-engine` | Everything so far in one class: build once, then answer each question with up to 3 sources | `python pipeline.py` |
| `09-api` | A FastAPI server: `POST /api/query`, `GET /api/stats`, `GET /api/health` | `uvicorn main:app` |
| `10-chat-page` | A chat page at http://127.0.0.1:8000, served by the same server | `uvicorn main:app` |

### Intermediate

| Project | What it adds to Basic 10's app | Run it |
|---|---|---|
| `01-rag-chat-app` | The same answers, from a production-grade codebase: one package per layer behind interfaces, chosen in one place (`factory.py`); every setting in `config.yaml`, checked at start-up; typed errors, answered in one JSON shape; a trace ID on every log line of each request, a timed span per stage, and JSON logs in `logs/app.log`; on the page, each request as a row of boxes: the answer, its pipeline (each step in order, with its time), its time per step, its calls counted by kind, its logs and what the model was given; timeouts, retries and a deadline on every call to Gemini; health checks and a content security policy | `python main.py` |

### Advanced

| Project | What it adds to the basic one | Run it |
|---|---|---|
| `01-read-the-knowledge-base` | Every row checked; sensitive data (PII, PCI, secrets) redacted; duplicates removed; logging and command-line options; a report of every row skipped, removed, redacted or flagged, and why. `data/sample_it_kb_messy.csv` has a row for each case | `python knowledge_base_loader.py` |
| `02-documents-and-metadata` | Each article checked against a schema (Pydantic); typed labels with one spelling per value (`kb_settings.toml`); an ID that survives re-sorting; provenance in every Document; and only the articles added or changed since the last run passed on, removed ones listed. `data/sample_it_kb_labels.csv` has a row for each label problem, `data/sample_it_kb_next.csv` is the next export | `python knowledge_base_loader.py` |
| `03-chunking` | The articles passed on cut into chunks along their sections (Problem, Resolution, Notes), never across one, sized in tokens with a hard ceiling; a title-and-section header on each chunk; a stable `chunk_id`, a link to its parent section; repeated paragraphs removed, fragments merged, runs with no spaces cut, each reported. `pipeline.py` runs the steps; `data/sample_it_kb_chunking.csv` has an article for each case | `python pipeline.py` |
| `04-embeddings` | The chunks embedded by Gemini through a sensitive-data gate; a cache on disk (SQLite) so an unchanged chunk is never sent twice, two models never mixed; batches under the API's limits, two calls at a time; retries with backoff and jitter for a 429, a 5xx or a timeout, a clear stop for anything else (a used-up daily quota too); every vector checked; calls, tokens and time reported. `provider = "fake"` runs it with no key | `python pipeline.py` |
| `05-vector-store` | The chunks' points in Qdrant (on disk in the process, no server needed), written idempotently (a point's ID from its chunk_id); a changed article's old chunks and a removed article's points deleted; a dense and a sparse vector per point; payload indexes on the labels; each load checked; `--rebuild` fills a new collection behind the alias `it_kb` and moves the alias only if it passes, `--rollback` moves it back | `python pipeline.py` |
| `06-retriever` | A LangChain retriever: dense and sparse search fused by rank (RRF); label filters read from the question; a "no match" threshold; re-ranking (word overlap, or a cross-encoder); at most 2 chunks per article, picked by MMR; a question cache; a rewriting hook. `evaluation.py` measures Recall@5, MRR and nDCG for each variant on 52 labeled questions (`data/eval_questions.csv`) and tunes the threshold | `python pipeline.py --question "..."`; `python evaluation.py` |
| `07-grounded-answer` | Each question answered by Gemini as a structured answer (the answer, the chunks it cites, whether they were enough): citations checked against the chunks given; an honest "not covered" instead of a guess; a chunk that speaks to the model kept out, the rest delimited; a token budget of whole chunks; a versioned prompt file; the answer redacted; an optional faithfulness judge. `data/sample_it_kb_injected.csv` plants an injected instruction | `python pipeline.py --question "..."` |
| `08-rag-engine` | The retriever and the answerer as one dependable core: parts passed in, settings from the file or the environment (`KB__...`); a deadline on every question; circuit breakers on the store and the model; an answer cache (exact and by meaning, scoped to the prompt, model and knowledge base, with an expiry); a trace per question; follow-ups rewritten with the conversation; honest stats | `python pipeline.py --question "..." --question "and on Mac?"` |
| `09` to `12` | Planned: each folder's README gives its plan (hybrid search and re-ranking, checked citations and injection defenses, tracing, auth and rate limits, containers and CI, an evaluation suite). See the [roadmap](Advanced/README.md) | (no code yet) |

## What you need

- **Python 3.11 or newer** (3.12 or newer for `Entry/V1`, `Entry/V3` and `RAG series`, for the NumPy they pin), and
  in each project: `python -m venv .venv`, activate it, then `pip install -r requirements-dev.txt`. Each project pins
  the packages it names to exact versions. On Windows with long paths off, keep the path of the repo root to 87
  characters or fewer: a path in a project's `.venv` can be 172 characters longer (in Intermediate/01; 168 in Basic
  07), and Windows refuses a path of 260 characters or more.
- **For `Entry`, a GitHub Codespace**: on Windows with long paths off, its Jupyter packages can fail to install when
  the repo sits deep in your folders (a path of 260 characters or more; each version's README has the details). It
  needs no key.
- **For `RAG series`, a browser and a Google account**: its notebooks open in Google Colab from their README's
  **Open in Colab** button.
- **A Gemini API key, from project 04 on (and for Intermediate/01)**, set up as in the tutorials (`tutorials/09-gemini-key`): copy the project's
  `.env.example` to `.env` and put the key after `GOOGLE_API_KEY=`. Every call to Gemini uses your key's quota.
  Without a key, the scripts stop with a message that says what to do. On the free tier, Gemini embeds at most 100
  texts a minute, and each text in a batch counts: a run of 04 to 10 embeds about 30.
- **No Docker and no database server**: Qdrant runs inside the scripts and keeps its points in memory.
- **Tests**: `python -m pytest -m "not live"` in a project's folder runs the plain tests: they use stand-ins for
  Gemini, so they need no key. The live tests call the real Gemini and run only when a key is set. From 07 on, a
  project's live tests together embed more than 100 texts, so on the free tier run them one file at a time, a minute
  apart (`python -m pytest -m live tests/<file>`, as its README shows).

## Run a project in one step

From the repo root, give `run.py` a project's level and folder name:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/01-read-the-knowledge-base
python "projects/RAG/IT Knowledge Base/run.py" Advanced/01-read-the-knowledge-base --log-level DEBUG   # options go to the project
```

It does a project's setup steps for you, the same on Windows, macOS, Linux and GitHub Codespaces: it creates the
project's `.venv` the first time (about a minute, with the install), installs its `requirements-dev.txt` into it,
copies its `.env.example` to `.env` if the project has one and no `.env` yet, then runs the project's command from the
table above, in the project's folder, with the venv's Python, so there's nothing to activate. After the first time it
takes a few seconds. It doesn't know your Gemini key: a new `.env` holds only a placeholder, so when `GOOGLE_API_KEY`
isn't in the environment either (from a Codespaces secret, say), it stops there and says to put your key in `.env`,
then run it again. `python "projects/RAG/IT Knowledge Base/run.py" --help` lists every project's name. `Entry` and
`RAG series` aren't in it: their projects are notebooks, run in VS Code or Colab, as their READMEs say.

## Built with

LangChain (`langchain-core`, `langchain-text-splitters`, `langchain-google-genai`, `langchain-qdrant`), Gemini,
Qdrant, FastAPI and pytest; `Intermediate` also uses Pydantic and PyYAML for its settings. `Entry` uses sentence-transformers, Chroma and Jupyter in place of LangChain, Gemini,
Qdrant and FastAPI. `RAG series` uses sentence-transformers and scikit-learn.

## The data

Every Basic, Intermediate and Advanced project uses the same knowledge base, `data/sample_it_kb.csv`: 10 made-up IT support
articles (VPN, MFA, Wi-Fi, printers and more) with no real people's details. It comes unchanged from the course repo,
[Brianletort/KBs-For-RAGs](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2/data), whose README marks
its contents for educational use. The `Entry` and `RAG series` notebooks use a few sentences of their own, written
in their code.
