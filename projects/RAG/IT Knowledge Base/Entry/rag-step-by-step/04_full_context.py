# Step 4: no RAG. Sends every document to the model with each question.
# Next: 05_chunk_documents.py

from langchain_ollama import OllamaLLM
from pathlib import Path

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"

llm = OllamaLLM(model=CHAT_MODEL, base_url=OLLAMA)

# Instructions that tell the model how to answer
instructions = """Answer the question using ONLY the context below.
If the answer isn't in the context, say "I don't know"."""

# Read the entire contents of every Markdown file in the docs folder
documents = []

for file in Path("docs").glob("*.md"):
    text = file.read_text(encoding="utf-8")
    if text.strip():
        documents.append(text)

if not documents:
    raise SystemExit(
        "No text found. Add Markdown files to the 'docs' folder."
    )

# Combine all document contents into one context
context = "\n\n".join(documents)
print(f"Loaded {len(documents)} documents into context.\n")

# 2. Ask the model to generate a response
def ask_generate(prompt):
    return llm.invoke(prompt)

# 3. Put the instructions, the context and the question together in one prompt
def build_prompt(context, question):
    return "\n\n".join([instructions, f"Context:\n{context}", f"Question: {question}"])

# 4. Keep accepting questions
while True:
    question = input("Ask (or type 'exit'): ").strip()

    if question.lower() == "exit":
        break

    if not question:
        continue

    # Build the prompt and show what is being sent to the model
    prompt = build_prompt(context, question)
    print(f"\nBelow is the prompt sent to LLM \n{prompt}\n")

    # Generate and display the answer
    answer = ask_generate(prompt)
    print(f"\n{answer}\n")

##-----------
# Question: Where do I take old batteries?
# Answer:   "According to the context, you should take old batteries to the recycling center on Oak Street,
#            which is open Tuesday to Saturday from 9am to 4pm."
#
# Step 3 could not answer this: its context was two library paragraphs typed into the code.
# Step 4 reads every file in docs, so the recycling guide is in the prompt and the model answers from it.
# The same answer came back on a second run.

##-----------
# Question asked: "When should I change my password?"
# Answer: "I don't know. The context does not mention anything about passwords or changing them."
# But the handbook says: "Members who sign in to a public computer need to update credentials every Friday at the information desk."
#
# Why it missed:
# - No search happened here, neither keyword nor semantic. Step 4 sends every document with every question,
#   so the model did see the credentials sentence (its answer mentioned the library, the pool and recycling).
# - The model read it literally: llama3.2 is a small model and did not treat "password" as meaning "credentials".
# - The instructions say use ONLY the context and say "I don't know", which pushes a small model to refuse
#   when the words don't match.
# - The question is vague: "my password" doesn't say which password, and the sentence is only about public computers.
#
# Tried with the same prompt, twice each:
# - "When should I change my password?"                 -> "I don't know" both times
# - "When should I change my public computer password?" -> one answer, one "I don't know"
# - "When should I update my credentials?"              -> "Every Friday at the information desk" both times
#
# So this is a generation miss (the model had the text but could not relate "password" to "credentials"), not a retrieval miss.

##-----------
# The problem with sending the entire context: the bigger the context, the more tokens, the more context bloat
# and the lower the quality. Every question carries every document, even the ones that have nothing to do with it.
#
# Measured here with "How much does a single swim cost for a 12-year-old?", twice each:
# - All three documents (645 tokens): about 21 seconds just to read the prompt, and both answers were wrong:
#   "I don't know. The context doesn't specify an age limit for children under 16 that is less than 12 years old ..."
# - Only the "Entry fees" paragraph (103 tokens): about 2 seconds, and both answers were "$3".
# Same model, same question, same instructions. The only difference is the extra text around the answer.
#
# It gets worse as documents are added:
# - Slower and costlier: every question pays to read every document again.
# - The window fills up: Ollama gives llama3.2 a 4,096-token window here, about six times our three documents.
#   Past that, Ollama cuts the prompt without raising an error (see the error handling section in 00_start_here.html).
# - Lower quality: the right sentence gets lost among unrelated ones, as the swim question shows.

##-----------
# Alternative 1: keyword search. Send only the chunks that contain the question's words.
# It works when the words match exactly: "laptop" or "batteries" finds the right chunk.
# It fails when the same meaning uses different words: the question "change my password" shares no word
# with the handbook's "update credentials", so that chunk is never found.

##-----------
# Alternative 2: store the chunks as vectors in a regular database. A regular index (B-tree) finds exact values
# or ranges, such as id = 42 or price < 10. It cannot find "the closest vector" to a question, so without a vector
# index the database compares the question with every row, which gets slow with millions of rows.
# Extensions such as pgvector add a vector index to PostgreSQL, which makes that search fast.

##-----------
# Alternative 3: RAG. Turn every chunk into a vector once (step 7). For each question, turn the question into
# a vector, find the few closest chunks by meaning, and send only those to the model (step 8).
# With 15 chunks, comparing against every vector in memory with NumPy is enough (that is what step 8 does). A vector database only matters with many more chunks,
# or to save the vectors instead of making them again every run.

##-----------
# Ask these questions (each gave the right answer in 2 runs out of 2)
#   Where do I take old batteries?          -> To the recycling center on Oak Street, open Tuesday to Saturday from 9am to 4pm.
#   When is the pool closed for cleaning?   -> Every Wednesday from 1pm to 3pm.
