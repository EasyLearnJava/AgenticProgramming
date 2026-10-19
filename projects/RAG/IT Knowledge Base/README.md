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

Each folder is a project of its own: it holds the app as built so far plus one new piece, runs on its own, and has
its own tests.

| Project | What it adds | Run it |
|---|---|---|
| `01-read-the-knowledge-base` | The CSV file of 10 articles read into LangChain `Document`s by a document loader | `python read_kb.py` |
| `02-documents-and-metadata` | Each article's text to search (title, problem, resolution, notes) kept apart from its labels (system, category, priority, tags) | `python knowledge_base.py` |
| `03-chunking` | The articles cut into chunks of at most 512 characters with `RecursiveCharacterTextSplitter`: 28 in all | `python chunking.py` |
| `04-embeddings` | Text turned into vectors by Gemini (`gemini-embedding-001`, 768 numbers), and the articles ranked by cosine similarity to a question | `python similarity.py` |
| `05-vector-store` | The chunks stored in Qdrant, in memory, through `QdrantVectorStore`, and searched by meaning | `python vector_store.py` |
| `06-retriever` | The store as a retriever, a Runnable that gives the 5 closest chunks for a question | `python retriever.py` |
| `07-grounded-answer` | The RAG chain: the chunks and the question go into a prompt, and Gemini (`gemini-3.5-flash-lite`) answers from them only | `python rag_chain.py` |
| `08-rag-engine` | Everything so far in one class: build once, then answer each question with up to 3 sources | `python rag_engine.py` |
| `09-api` | A FastAPI server: `POST /api/query`, `GET /api/stats`, `GET /api/health` | `uvicorn main:app --reload` |
| `10-chat-page` | A chat page at http://127.0.0.1:8000, served by the same server | `uvicorn main:app --reload` |
| `11-qdrant-in-docker` | Qdrant as a server in Docker, which keeps the chunks between runs, so they're embedded only once | `docker compose up -d`, then `uvicorn main:app --reload` |
| `12-tuning` | The search scored on 10 test questions for three chunk sizes and three values of k; with `--answers`, one question answered from 1 chunk and from 5 | `python tuning.py` |

## What you need

- **Python 3.11 or newer**, and in each project: `python -m venv .venv`, activate it, then
  `pip install -r requirements-dev.txt`. Each project pins its packages to exact versions.
- **A Gemini API key, from project 04 on**, set up as in the tutorials (`tutorials/09-gemini-key`): copy the project's
  `.env.example` to `.env` and put the key after `GOOGLE_API_KEY=`. Every call to Gemini uses your key's quota.
  Without a key, the scripts stop with a message that says what to do.
- **Docker, for projects 11 and 12**: `docker compose up -d` in the project's folder starts the Qdrant server that
  their `rag_engine.py` and `main.py` use. (`tuning.py` runs Qdrant in memory and doesn't need it.)
- **Tests**: `python -m pytest` in a project's folder. The plain tests use stand-ins for Gemini, so they need no key;
  the live tests call the real Gemini and run only when a key is set.

## Built with

LangChain (`langchain-core`, `langchain-text-splitters`, `langchain-google-genai`, `langchain-qdrant`), Gemini,
Qdrant, FastAPI and pytest.

## The data

Every project uses the same knowledge base, `data/sample_it_kb.csv`: 10 made-up IT support articles (VPN, MFA,
Wi-Fi, printers and more) with no real people's details. It comes unchanged from the course repo,
[Brianletort/KBs-For-RAGs](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2/data), whose README marks
its contents for educational use.
