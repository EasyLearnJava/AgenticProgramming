# Step 10: the same as step 9, but an OpenAI model writes the answer instead of llama3.2.
# Search still runs on your laptop with Ollama. Only the prompt (instructions, closest chunk, question) goes to OpenAI.
# Before running, paste your OpenAI API key into OPENAI_API_KEY in the settings below.
# Next: 11_vector_store.py

import numpy as np
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_openai import ChatOpenAI
from pathlib import Path

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "gpt-4.1-mini"  # the OpenAI model that writes the answer

# Paste your OpenAI API key between the quotes.
# Remove it again before you commit, push or share this file: anyone who sees the key can use it on your account.
OPENAI_API_KEY = ""
EMBED_MODEL = "nomic-embed-text"
DOCS_FOLDER = Path("docs")
TOP_K = 2  # how many of the closest chunks to send to the LLM

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

if not OPENAI_API_KEY:
    raise SystemExit(
        "Paste your OpenAI API key into OPENAI_API_KEY in the settings at the top of this file."
    )

embedding_model = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA)
llm = ChatOpenAI(model=CHAT_MODEL, api_key=OPENAI_API_KEY)


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
    # A chat model returns a message; .content is its text
    return llm.invoke(prompt).content


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
# Ask these questions
#   When is the pool closed for cleaning?                 -> Every Wednesday from 1pm to 3pm.
#   How much does a single swim cost for a 12-year-old?   -> $3
# Both were checked with step 9 (llama3.2), which sends the same prompt. Not yet run with OpenAI:
# the account had no API credits when this step was written.
