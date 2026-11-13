# RAG Step by Step

A small question answering app over three short documents in `docs`
(a library handbook, a swimming pool guide and a recycling guide),
built up in twelve steps. Read and run the files in number order.
Open `00_start_here.html` in a browser for a short guide to every step.

## Reading order

| Step | File | What it shows |
|---|---|---|
| 1 | `01_ask_llm.py` | Sends a question to the model through LangChain and prints its response. No documents yet. |
| 2 | `02_add_prompt.py` | Wraps the question in a prompt that tells the model how to answer. |
| 3 | `03_hardcoded_context.py` | Sends a small context, typed into the code, with the question. |
| 4 | `04_full_context.py` | No RAG: sends every document to the model with each question. |
| 5 | `05_chunk_documents.py` | Splits the documents into chunks at each blank line and prints them. |
| 6 | `06_add_metadata.py` | Labels each chunk with its source, title, section, ID, owner and access. |
| 7 | `07_embed_chunks.py` | Turns each chunk into a vector (768 numbers) and prints the chunk with its vector. |
| 8 | `08_search_by_meaning.py` | Turns a question into a vector and prints every chunk's score and the closest chunk. No LLM. |
| 9 | `09_search_and_answer.py` | Step 8 plus the LLM: sends the closest chunk (TOP_K = 1) with the question and prints the answer. |
| 10 | `10_search_and_answer_openai.py` | Step 9 with an OpenAI model writing the answer. Needs your own OpenAI API key. |
| 11 | `11_vector_store.py` | Step 9 with LangChain's InMemoryVectorStore: it searches, filters on labels and saves the vectors to a file. |
| 12 | `12_rag_evaluation.py` | Runs the 10 test questions below through step 11, checks each answer, prints the score and saves it to `results/`. |

## Setup

`00_start_here.html` walks through setup on Windows step by step. In short:

1. Install [Ollama](https://ollama.com/download) and [uv](https://docs.astral.sh/uv/).
2. Download the two models:
   ```
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```
3. From this folder, install Python 3.13 and the packages:
   ```
   uv sync
   ```

## Run

With Ollama running, from this folder:

```
uv run 01_ask_llm.py
uv run 02_add_prompt.py
uv run 03_hardcoded_context.py
uv run 04_full_context.py
uv run 05_chunk_documents.py
uv run 06_add_metadata.py
uv run 07_embed_chunks.py
uv run 08_search_by_meaning.py
uv run 09_search_and_answer.py
uv run 10_search_and_answer_openai.py
uv run 11_vector_store.py
uv run 12_rag_evaluation.py
```

## Test questions

| Question | Expected answer |
|---|---|
| Can I drink water in a reading room? | Yes, if the water is in a closed bottle. |
| Can a 15-year-old borrow a laptop? | No. Laptop borrowers must be members aged 18 or older. |
| Can I take a library laptop home? | No. Laptops may only be used inside the library. |
| How often do I need to update my public computer credentials? | Every Friday, at the information desk. |
| Is the library open on Sundays? | No. The library is closed on Sundays. |
| When is the pool closed for cleaning? | Every Wednesday from 1pm to 3pm. |
| How much does a single swim cost for a 12-year-old? | $3. Children under 16 pay $3. |
| Where do I take old batteries? | To the recycling center on Oak Street, open Tuesday to Saturday from 9am to 4pm. |
| Can plastic bags go in the blue bin? | No. Plastic bags must not go in the blue bin. |
| Can I bring my dog to the pool? | “I don’t know.” The guides do not mention dogs. |
