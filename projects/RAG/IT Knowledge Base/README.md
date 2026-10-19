# IT Knowledge Base

An IT help-desk app that answers questions from a knowledge base of IT support articles, built one small step at a
time. In the finished app you ask "How do I fix VPN connection timeouts?", and it finds the matching articles and has
a language model write the answer from them, showing which articles it used. That's a RAG app (retrieval-augmented
generation).

The steps rebuild the *IT Knowledge Base RAG Application* from the Pluralsight course *Integrating Knowledge Bases for
RAGs* ([its code](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2)), one piece at a time, so that each
piece runs, and can be checked, on its own.

## The steps

| Step | What it adds |
|---|---|
| [01 · Read the knowledge base](01-read-the-knowledge-base/README.md) | The CSV file of 10 IT support articles, read into a pandas table and printed |
| 02 · Turn rows into Documents | Each article becomes a LlamaIndex `Document`: the text to search, plus labels that say where it came from |
| 03 · Chunking | Documents split into smaller pieces, with some overlap |
| 04 · Embeddings | Text turned into vectors, lists of numbers that are close when the meanings are close |
| 05 · The vector database | Qdrant, in memory: storing vectors and finding the nearest ones |
| 06 · Retrieval | The pieces that best match a question, found through LlamaIndex |
| 07 · A grounded answer | The question and those pieces go to a language model, which answers from them |
| 08 · The RAG engine | Steps 01 to 07 in one class, giving an answer and its sources |
| 09 · The API | A FastAPI server that answers `POST /api/query` |
| 10 · The chat page | A Next.js page that asks questions and shows the answers with their sources |
| 11 · Qdrant in Docker | A vector database that keeps its data between restarts |
| 12 · Tuning | Chunk size, the number of pieces found and the model's temperature, changed one at a time |

Only step 01 is written so far. Steps 01 to 03 need no API key; the later ones call an embedding model and a language
model.

## The data

Every step uses the same knowledge base, `data/sample_it_kb.csv`: 10 made-up IT support articles (VPN, MFA, Wi-Fi,
printers and more) with no real people's details. It comes unchanged from the course repo,
[Brianletort/KBs-For-RAGs](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2/data), whose README marks
its contents for educational use.

## How a step is laid out

Each step is a folder that runs on its own, like the tutorials: a script with numbered comments, a README that goes
through it (what you'll build and learn, how it works, how to run and test it, what can go wrong), two pictures, and
tests. Open a step's README and follow its "Run it" section. The folder name `IT Knowledge Base` has spaces in it, so
put paths in quotes when you `cd`.
