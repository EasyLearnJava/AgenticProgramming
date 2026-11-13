# Step 9: search by meaning, then send the closest chunk to the LLM to write the answer.
# Next: 10_search_and_answer_openai.py

import numpy as np
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from pathlib import Path

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"
EMBED_MODEL = "nomic-embed-text"
DOCS_FOLDER = Path("docs")
TOP_K = 1  # how many of the closest chunks to send to the LLM

# Who looks after each document (example values for our sample files)
DOCUMENT_OWNERS = {
    "handbook.md": "Library team",
    "recycling.md": "Waste services team",
    "swimming_pool.md": "Pool team",
}

# Who may see the documents. For now every document is open to everyone.
ACCESS = "everyone"

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


# 4. Turn every chunk's text into a vector, in one call to the embedding model
def embed_chunks(chunks):
    return np.array(embedding_model.embed_documents([chunk.page_content for chunk in chunks]))


# 5. Turn the question into a vector, with the same embedding model
def embed_question(question):
    return np.array(embedding_model.embed_query(question))


# 6. Score every chunk against the question with cosine similarity, and keep the closest TOP_K
def search(question_vector, chunks, chunk_vectors, k=TOP_K):
    scores = chunk_vectors @ question_vector / (
        np.linalg.norm(chunk_vectors, axis=1) * np.linalg.norm(question_vector)
    )
    closest_first = np.argsort(scores)[::-1]
    return [(chunks[i], scores[i]) for i in closest_first[:k]]


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


# 10. Embed the chunks once, then keep accepting questions
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

    # Search: find the closest chunks
    question_vector = embed_question(question)
    found = search(question_vector, chunks, chunk_vectors)
    print_found(found)

    # Build the prompt and show what is being sent to the model
    prompt = build_prompt(found, question)
    print(f"\nBelow is the prompt sent to LLM \n{prompt}\n")

    # Generate and display the answer
    answer = ask_generate(prompt)
    print(f"\n{answer}\n")

##-----------
# Question: How much does a single swim cost for a 12-year-old?
#
#   Closest 1 chunk(s):
#   0.80   swimming_pool.md#2   Entry fees
#   Answer: "$3"
#
# In step 4, with all three documents in the prompt, this question was answered wrong both times.
# With only the one chunk that holds the answer, the model gets it right.

##-----------
# Question: When should I change my password?
#
#   Closest 1 chunk(s):
#   0.55   handbook.md#3        Public computers
#   Answer: "I don't know."
#
# Search found the right chunk, and the model had the credentials sentence in front of it,
# but it still did not relate "password" to "credentials". The same miss as in step 4.

##-----------
# Question: How much is a monthly pool pass, and when is the pool open on weekends?
#
# This question has two parts, and they are in two different chunks:
# - the price is in "Entry fees":       "A monthly pass costs $45."
# - the hours are in "Opening hours":   "... from 8am to 6pm on Saturday and Sunday."
#
# With TOP_K = 1 only the closest chunk is sent:
#
#   Closest 1 chunk(s):
#   0.72   swimming_pool.md#1   Opening hours
#   Answer, run 1: "I don't know."
#   Answer, run 2: "I don't know how much is the monthly pool pass. ... On Saturday: 8am to 6pm, On Sunday: 8am to 6pm"
#
# "Entry fees" scored 0.70, just behind, so it was left out. The price never reached the model,
# so at best it could answer half of the question.
#
# The same question with more chunks (TOP_K changed to 2, then 3), two runs each:
#
#   | TOP_K | Chunks sent                                  | Run 1                     | Run 2                  |
#   |-------|----------------------------------------------|---------------------------|------------------------|
#   | 1     | Opening hours                                | "I don't know."           | Hours only             |
#   | 2     | Opening hours, Entry fees                    | Confused, contradicts     | $45 and 8am to 6pm     |
#   |       |                                              | itself                    |                        |
#   | 3     | Opening hours, Entry fees, pool Introduction | $45 and 8am to 6pm        | $45 only               |
#
# With 2 or 3 chunks both answers are in the prompt, and the model can answer the whole question.
# It still doesn't do so every time: a small model with randomness can drop half the answer.

##-----------
# TOP_K = 1 is not always the best option
#
# - It works when the answer sits in one chunk and that chunk comes first (the swim price above).
# - It fails when the answer is spread over two chunks (the monthly pass question).
# - It fails when the right chunk comes a close second. For the password question the right chunk won
#   only 0.55 against 0.52; a slightly different wording could have put it second, and then it is never sent.
#
# Too many chunks is a problem too: step 4 sent everything and got slower and less accurate answers.
#
# What usually works best:
# - Start with a few chunks, commonly 3 to 5. Enough to hold an answer that is split across chunks,
#   few enough to keep the prompt short.
# - Measure, don't guess: run the same test questions with TOP_K = 1, 3 and 5 and keep the value that
#   answers the most of them correctly.
# - Optionally drop chunks whose score is far below the best one, so weak matches don't fill the prompt.
#   With the monthly pass question, 0.72 and 0.70 are close (keep both); the third chunk, the pool
#   Introduction at 0.60, holds no facts and only adds text.

##-----------
# Ask these questions (each gave the right answer in 3 runs out of 3)
#   When is the pool closed for cleaning?                 -> Every Wednesday from 1pm to 3pm.
#   How much does a single swim cost for a 12-year-old?   -> $3
