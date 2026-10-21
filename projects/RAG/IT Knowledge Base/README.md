# IT Knowledge Base

An IT help-desk assistant that answers questions from a knowledge base of IT support articles, built with LangChain
and Gemini, one step at a time. You ask "How do I fix VPN connection timeouts?"; it finds the parts of the articles
that match, and Gemini writes the answer from those parts only, naming the articles it used. That's RAG:
retrieval-augmented generation.

```text
question ─> embed it ─> find the closest chunks in Qdrant ─> prompt: the chunks + the question ─> Gemini ─> answer + sources
```

It rebuilds the *IT Knowledge Base RAG Application* from the Pluralsight course *Integrating Knowledge Bases for
RAGs* ([its code](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2)), with LangChain in place of
LlamaIndex, Gemini in place of OpenAI, and a plain HTML page served by FastAPI in place of Next.js.

## The projects

The projects come in two levels:

- **`Basic/`**: the whole app, 01 to 12, one step at a time, each on the happy path: the data is assumed to be good.
- **`Advanced/`**: the same projects done again, production grade: each checks its input, handles what goes wrong,
  and reports it. 01 is built; 02 to 12 are planned, each with a README giving its plan, and
  [Advanced/README.md](Advanced/README.md) is the roadmap.

Each folder is a project of its own: it holds the app as built so far plus one new piece, runs on its own, and has
its own tests. Projects 01 to 05 get the knowledge base ready to be searched (read, split, chunk, embed, store), with
no question anywhere; the user's question comes in at 06, and 07 onward answer it.

### Basic

| Project | What it adds | Run it |
|---|---|---|
| `01-read-the-knowledge-base` | The CSV file of 10 articles read into LangChain `Document`s by a document loader | `python pipeline.py` |
| `02-documents-and-metadata` | Each article's text to search (title, problem, resolution, notes) kept apart from its labels (system, category, priority, tags) | `python pipeline.py` |
| `03-chunking` | The articles cut into chunks of at most 512 characters with `RecursiveCharacterTextSplitter`: 28 in all | `python pipeline.py` |
| `04-embeddings` | The 28 chunks turned into vectors by Gemini (`gemini-embedding-001`, 768 numbers each), in one call. No question yet | `python pipeline.py` |
| `05-vector-store` | The chunks stored in a Qdrant server in Docker (or in memory), through `QdrantVectorStore`: one point per chunk, with its vector, text and labels, shown in Qdrant's dashboard | `docker compose up -d`, then `python pipeline.py` |
| `06-retriever` | The user's question: embedded, then searched in Qdrant for the 5 closest chunks; then both in one call with a retriever, a Runnable | `python retriever.py` |
| `07-grounded-answer` | The RAG chain: the chunks and the question go into a prompt, and Gemini (`gemini-3.5-flash-lite`) answers from them only | `python rag_chain.py` |
| `08-rag-engine` | Everything so far in one class: build once, then answer each question with up to 3 sources | `python rag_engine.py` |
| `09-api` | A FastAPI server: `POST /api/query`, `GET /api/stats`, `GET /api/health` | `uvicorn main:app --reload` |
| `10-chat-page` | A chat page at http://127.0.0.1:8000, served by the same server | `uvicorn main:app --reload` |
| `11-qdrant-in-docker` | Qdrant as a server in Docker, which keeps the chunks between runs, so they're embedded only once | `docker compose up -d`, then `uvicorn main:app --reload` |
| `12-tuning` | The search scored on 10 test questions for three chunk sizes and three values of k; with `--answers`, one question answered from 1 chunk and from 5 | `python tuning.py` |

### Advanced

| Project | What it adds to the basic one | Run it |
|---|---|---|
| `01-read-the-knowledge-base` | Every row checked; sensitive data (PII, PCI, secrets) redacted; duplicates removed; logging and command-line options; a report of every row skipped, removed, redacted or flagged, and why. `data/sample_it_kb_messy.csv` has a row for each case | `python knowledge_base_loader.py` |
| `02` to `12` | Planned: each folder's README gives its plan (validated schemas, token-sized chunks, retries and caching, hybrid search and re-ranking, checked citations and injection defenses, tracing, auth and rate limits, containers and CI, an evaluation suite). See the [roadmap](Advanced/README.md) | (no code yet) |

## What you need

- **Python 3.11 or newer**, and in each project: `python -m venv .venv`, activate it, then
  `pip install -r requirements-dev.txt`. Each project pins its packages to exact versions.
- **A Gemini API key, from project 04 on**, set up as in the tutorials (`tutorials/09-gemini-key`): copy the project's
  `.env.example` to `.env` and put the key after `GOOGLE_API_KEY=`. Every call to Gemini uses your key's quota.
  Without a key, the scripts stop with a message that says what to do.
- **Docker, for projects 11 and 12**: `docker compose up -d` in the project's folder starts the Qdrant server that
  their `rag_engine.py` and `main.py` use. (`tuning.py` runs Qdrant in memory and doesn't need it.) Project 05 uses it
  too, to show the stored points in Qdrant's dashboard; it can also run in memory, without Docker.
- **Tests**: `python -m pytest` in a project's folder. The plain tests use stand-ins for Gemini, so they need no key;
  the live tests call the real Gemini and run only when a key is set.

## Run a project in one step

From the repo root, give `run.py` a project's level and folder name:

```bash
python "projects/RAG/IT Knowledge Base/run.py" Basic/01-read-the-knowledge-base
python "projects/RAG/IT Knowledge Base/run.py" Advanced/01-read-the-knowledge-base --log-level DEBUG   # options go to the project
```

It does a project's setup steps for you, the same on Windows, macOS, Linux and Codespaces: it creates the project's
`.venv` the first time (about a minute, with the install), installs its `requirements-dev.txt` into it, then runs the
project's command from the table above, in the project's folder, with the venv's Python, so there's nothing to
activate. After the first time it takes a few seconds. It doesn't set up a Gemini key or start Docker: do those first,
as above. `python "projects/RAG/IT Knowledge Base/run.py" --help` lists every project's name.

## Built with

LangChain (`langchain-core`, `langchain-text-splitters`, `langchain-google-genai`, `langchain-qdrant`), Gemini,
Qdrant, FastAPI and pytest.

## The data

Every project uses the same knowledge base, `data/sample_it_kb.csv`: 10 made-up IT support articles (VPN, MFA,
Wi-Fi, printers and more) with no real people's details. It comes unchanged from the course repo,
[Brianletort/KBs-For-RAGs](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2/data), whose README marks
its contents for educational use.
