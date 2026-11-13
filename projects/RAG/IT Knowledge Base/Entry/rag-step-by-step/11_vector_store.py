# Step 11: step 9 with a vector store. The store keeps each chunk's vector, text, labels and ID,
# does the search for us, filters on labels, and saves everything to a file so the next run skips embedding.
# Next: 12_rag_evaluation.py

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from pathlib import Path

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"
EMBED_MODEL = "nomic-embed-text"
DOCS_FOLDER = Path("docs")
TOP_K = 1  # how many of the closest chunks to send to the LLM

# Where the vector store is saved. Delete this file after changing anything in docs, so it is built again.
STORE_FILE = Path("vector_store.json")

# Who looks after each document (example values for our sample files)
DOCUMENT_OWNERS = {
    "handbook.md": "Library team",
    "recycling.md": "Waste services team",
    "swimming_pool.md": "Pool team",
}

# Who may see the documents. For now every document is open to everyone.
ACCESS = "everyone"

# Search only chunks whose access label matches this
ALLOWED_ACCESS = "everyone"

# Instructions that tell the model how to answer
instructions = """Answer the question using ONLY the context below.
If the answer isn't in the context, say "I don't know"."""

embedding_model = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA)
llm = OllamaLLM(model=CHAT_MODEL, base_url=OLLAMA)


# 2. Read the entire contents of every Markdown file in the docs folder, keyed by file name
def load_documents():
    documents = {}

    for file in sorted(DOCS_FOLDER.glob("*.md")):
        text = file.read_text(encoding="utf-8")
        if text.strip():
            documents[file.name] = text

    if not documents:
        raise SystemExit(
            "No text found. Add Markdown files to the 'docs' folder."
        )
    return documents


# 3. Split each document into chunks wherever there is a blank line, and label each chunk
def split_into_chunks(documents):
    chunks = []

    for source, text in documents.items():
        title = source
        section = ""
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]

        for position, paragraph in enumerate(paragraphs):
            first_line = paragraph.splitlines()[0]

            # A "# " line is the document's title, and the chunk under it is the introduction
            if first_line.startswith("# "):
                title = first_line[2:]
                section = "Introduction"
            # A "## " line starts a new section; a later paragraph without a heading keeps it
            elif first_line.startswith("## "):
                section = first_line[3:]

            chunks.append(Document(
                page_content=paragraph,
                metadata={
                    "source": source,
                    "title": title,
                    "section": section,
                    "chunk_id": f"{source}#{position}",
                    "owner": DOCUMENT_OWNERS.get(source, "unknown"),
                    "access": ACCESS,
                },
            ))
    return chunks


# 4. Build the vector store: it embeds every chunk and keeps the vector with its text, labels and ID
def build_vector_store(chunks):
    vector_store = InMemoryVectorStore(embedding=embedding_model)
    vector_store.add_documents(chunks, ids=[chunk.metadata["chunk_id"] for chunk in chunks])
    return vector_store


# 5. Load the saved vector store, or build it and save it the first time
def load_or_build_vector_store():
    if STORE_FILE.exists():
        vector_store = InMemoryVectorStore.load(str(STORE_FILE), embedding=embedding_model)
        print(f"Loaded {len(vector_store.store)} saved chunks from {STORE_FILE}. Nothing embedded.\n")
        return vector_store

    chunks = split_into_chunks(load_documents())
    vector_store = build_vector_store(chunks)
    vector_store.dump(str(STORE_FILE))
    print(f"Embedded {len(chunks)} chunks and saved them to {STORE_FILE}.\n")
    return vector_store


# 6. Search: the store embeds the question, scores the allowed chunks with cosine similarity,
#    and returns the closest TOP_K with their scores
def search(vector_store, question, k=TOP_K):
    return vector_store.similarity_search_with_score(
        question,
        k=k,
        filter=lambda chunk: chunk.metadata["access"] == ALLOWED_ACCESS,
    )


# 7. Put the instructions, the found chunks and the question together in one prompt
def build_prompt(found, question):
    context = "\n\n".join(chunk.page_content for chunk, score in found)
    return "\n\n".join([instructions, f"Context:\n{context}", f"Question: {question}"])


# 8. Ask the model to generate a response
def ask_generate(prompt):
    return llm.invoke(prompt)


# 9. Print the chunks that were found, with their scores
def print_found(found):
    print(f"\nClosest {len(found)} chunk(s):")
    for chunk, score in found:
        print(f"{score:.2f}   {chunk.metadata['chunk_id']:20} {chunk.metadata['section']}")


# 10. Load or build the vector store once, then keep accepting questions
vector_store = load_or_build_vector_store()

while True:
    question = input("Ask (or type 'exit'): ").strip()

    if question.lower() == "exit":
        break

    if not question:
        continue

    # Search: find the closest chunks
    found = search(vector_store, question)
    print_found(found)

    # Build the prompt and show what is being sent to the model
    prompt = build_prompt(found, question)
    print(f"\nBelow is the prompt sent to LLM \n{prompt}\n")

    # Generate and display the answer
    answer = ask_generate(prompt)
    print(f"\n{answer}\n")

##-----------
# What changed from step 9
#
#   | Step 9                                         | Step 11                                             |
#   |------------------------------------------------|-----------------------------------------------------|
#   | embed_chunks(): our own call, vectors in NumPy | build_vector_store(): the store embeds and keeps    |
#   | embed_question() + search(): our cosine code   | search(): one call, similarity_search_with_score()  |
#   | Vectors lost when the program stops            | Saved to vector_store.json, loaded on the next run  |
#   | No filtering                                   | filter= keeps only chunks the user may see          |
#
# The answers don't change. Same embedding model, same cosine similarity, so the same chunks and scores:
#   "When should I change my password?"                   -> 0.55 Public computers, answer "I don't know."
#   "How much does a single swim cost for a 12-year-old?" -> 0.80 Entry fees, answer "$3"

##-----------
# Advantage 1: vectors are saved, so the next run doesn't embed again
#
#   First run:   "Embedded 15 chunks and saved them to vector_store.json."  about 5.1 seconds to start
#   Next runs:   "Loaded 15 saved chunks from vector_store.json. Nothing embedded."  about 2.1 seconds
#
# With 15 chunks that saves about 3 seconds. With 100,000 chunks it saves re-embedding all of them on every start.
# Each saved entry holds everything about one chunk, for example:
#   'swimming_pool.md#3': {'id': 'swimming_pool.md#3', 'vector': [768 numbers],
#                          'text': '## Children\nChildren under 10 must be watched ...',
#                          'metadata': {'source': 'swimming_pool.md', 'section': 'Children', 'access': 'everyone', ...}}
# The file is about 240 KB.
# The saved file does not notice when docs change. Delete vector_store.json after editing docs, so it is built again.

##-----------
# Advantage 2: filtering on labels, inside the search
#
# search() passes filter=lambda chunk: chunk.metadata["access"] == ALLOWED_ACCESS.
# Chunks that fail the filter are never scored, so they can never reach the LLM.
# Tried with ALLOWED_ACCESS = "staff" (no chunk has that label):
#   Closest 0 chunk(s):
#   Answer: "I don't know."
# With real access labels, the same line keeps staff-only documents away from other users.

##-----------
# Advantage 3: every chunk has an ID
#
# add_documents(..., ids=[chunk_id, ...]) stores each chunk under its chunk_id, such as "swimming_pool.md#3".
# One chunk can then be replaced or removed without rebuilding the rest:
#   vector_store.delete(ids=["swimming_pool.md#3"])

##-----------
# Advantage 4: less code to write
#
# The cosine formula, the sorting and the "keep the top K" logic from step 9 are now one call.

##-----------
# What it does NOT give
#
# - Better answers. It finds exactly the same chunks as step 9; the password question still gets "I don't know."
# - Faster search. InMemoryVectorStore still compares the question with every chunk, like step 9.
#   Databases such as Qdrant or Chroma add an index (HNSW) that checks only part of the chunks,
#   which matters with millions of chunks, not 15.
# - Sharing. It lives inside this one program. A database server can be used by many programs at once.

##-----------
# Ask these questions (each gave the right answer in 3 runs out of 3)
#   When is the pool closed for cleaning?                 -> Every Wednesday from 1pm to 3pm.
#   How much does a single swim cost for a 12-year-old?   -> $3
