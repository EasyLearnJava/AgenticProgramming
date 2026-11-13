# Step 8: search by meaning. Turn the question into a vector and find the closest chunk. No LLM yet.
# Next: 09_search_and_answer.py

import numpy as np
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from pathlib import Path

# 1. Settings
OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
DOCS_FOLDER = Path("docs")

# Who looks after each document (example values for our sample files)
DOCUMENT_OWNERS = {
    "handbook.md": "Library team",
    "recycling.md": "Waste services team",
    "swimming_pool.md": "Pool team",
}

# Who may see the documents. For now every document is open to everyone.
ACCESS = "everyone"

embedding_model = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA)


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


# 4. Turn every chunk's text into a vector, in one call to the embedding model
def embed_chunks(chunks):
    return np.array(embedding_model.embed_documents([chunk.page_content for chunk in chunks]))


# 5. Turn the question into a vector, with the same embedding model
def embed_question(question):
    return np.array(embedding_model.embed_query(question))


# 6. Score every chunk against the question with cosine similarity, closest first
def search(question_vector, chunks, chunk_vectors):
    scores = chunk_vectors @ question_vector / (
        np.linalg.norm(chunk_vectors, axis=1) * np.linalg.norm(question_vector)
    )
    closest_first = np.argsort(scores)[::-1]
    return [(chunks[i], scores[i]) for i in closest_first]


# 7. Print every chunk's score, then the closest chunk in full
def print_results(results):
    print("\nScore  Chunk")
    for chunk, score in results:
        print(f"{score:.2f}   {chunk.metadata['chunk_id']:20} {chunk.metadata['section']}")

    best_chunk, best_score = results[0]
    print(f"\nClosest chunk (score {best_score:.2f}):")
    print(best_chunk.page_content)
    print("Labels (metadata):")
    print(best_chunk.metadata)
    print()


# 8. Embed the chunks once, then keep accepting questions
documents = load_documents()
chunks = split_into_chunks(documents)
chunk_vectors = embed_chunks(chunks)
print(f"Embedded {len(chunks)} chunks from {len(documents)} documents.\n")

while True:
    question = input("Ask (or type 'exit'): ").strip()

    if question.lower() == "exit":
        break

    if not question:
        continue

    question_vector = embed_question(question)
    results = search(question_vector, chunks, chunk_vectors)
    print_results(results)

##-----------
# Question: When should I change my password?
#
#   Score  Chunk
#   0.55   handbook.md#3        Public computers
#   0.52   swimming_pool.md#4   Pool rules
#   0.51   handbook.md#2        Laptop loans
#   ...
#   0.43   recycling.md#2       What goes in the blue bin
#
#   Closest chunk (score 0.55):
#   ## Public computers
#   ... Members who sign in to a public computer need to update credentials every Friday at the information desk.
#
# The question and the chunk share no word: "change my password" against "update credentials".
# Search by meaning still found it. A keyword search would not.
# The lead is small, though: 0.55 against 0.52 for Pool rules. The closest chunk is not always far ahead.

##-----------
# Question: Can my kid swim without me?
#
#   Score  Chunk
#   0.68   swimming_pool.md#3   Children
#   0.59   swimming_pool.md#2   Entry fees
#   0.55   swimming_pool.md#4   Pool rules
#   0.47   swimming_pool.md#1   Opening hours
#   0.45   swimming_pool.md#0   Introduction
#   ...
#
# "kid" found "Children", and the top five are all from the pool guide.
# The Children chunk never says "pool", but "swim" and "children" were enough.

##-----------
# Question: Where do I take old batteries?
#
#   Score  Chunk
#   0.60   recycling.md#3       Batteries and electronics
#   0.55   recycling.md#1       Collection days
#   0.54   handbook.md#2        Laptop loans
#   ...
#
# Here the question and the chunk share the word "batteries", and it is a clear first.

##-----------
# How to read the scores:
# - The score is the cosine similarity: 1 means the same meaning, 0 means unrelated.
# - In practice every chunk scores something, here between about 0.3 and 0.7. A score is not a percentage.
# - Compare scores within one question, not across questions. 0.55 was the right chunk for the password
#   question, but for the batteries question "Collection days" also scored 0.55 and was the wrong chunk.
# - Search always returns a closest chunk, even for a question the documents can't answer.
#   Closest does not mean correct.

##-----------
# Search returns the whole chunk, not the answer.
#
# For "When should I change my password?" the closest chunk has three sentences:
#   1. Each visitor may use a public computer for 60 minutes per day.
#   2. If nobody is waiting, staff may approve one additional 30-minute session.
#   3. Members who sign in to a public computer need to update credentials every Friday at the information desk.
# Only sentence 3 answers the question. Sentences 1 and 2 come along because they are in the same chunk.
#
# Here a chunk is one short paragraph of about 50 words, so that is easy to read. Chunks are usually bigger:
# often 500 to 1,000 tokens, roughly 400 to 750 words, several paragraphs long. The question may be about one
# sentence in them. The user doesn't want 750 words; they want "Every Friday, at the information desk."
#
# Search can't do that part. It only measures how close each chunk is; it can't read the chunk or pick out a line.
# This is where an LLM comes in: we give it the question and the closest chunks, and it reads them, finds the
# part that answers the question, and writes a short answer in plain words.
#
#   Search finds WHERE the answer is (the chunk).  The LLM reads it and says WHAT the answer is.

##-----------
# Ask these questions (search gives the same result every time)
#   Where do I take old batteries?   -> closest chunk: recycling.md#3  Batteries and electronics  (0.60)
#   Can my kid swim without me?      -> closest chunk: swimming_pool.md#3  Children  (0.68)
