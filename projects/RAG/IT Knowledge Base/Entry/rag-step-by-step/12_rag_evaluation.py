# Step 12: evaluate step 11. Ask 10 prepared questions, check each answer for its key fact,
# print the score and save everything to the results folder. Run it again after each change and compare.

import json
import re
from datetime import datetime

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from pathlib import Path

# 1. Settings (the same as step 11)
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"
EMBED_MODEL = "nomic-embed-text"
DOCS_FOLDER = Path("docs")
TOP_K = 1  # how many of the closest chunks to send to the LLM

# Where the vector store is saved. Delete this file after changing anything in docs, so it is built again.
STORE_FILE = Path("vector_store.json")

# Where the evaluation results are saved
RESULTS_FOLDER = Path("results")

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

# Prepared questions (the same as README.md): the question, the answer we expect,
# and the key words a correct answer must contain
QUESTIONS = [
    ("Can I drink water in a reading room?", "Yes, if the water is in a closed bottle.", ["closed"]),
    ("Can a 15-year-old borrow a laptop?", "No. Laptop borrowers must be members aged 18 or older.", ["18"]),
    ("Can I take a library laptop home?", "No. Laptops may only be used inside the library.", ["inside"]),
    ("How often do I need to update my public computer credentials?", "Every Friday, at the information desk.", ["friday"]),
    ("Is the library open on Sundays?", "No. The library is closed on Sundays.", ["closed"]),
    ("When is the pool closed for cleaning?", "Every Wednesday from 1pm to 3pm.", ["wednesday"]),
    ("How much does a single swim cost for a 12-year-old?", "$3. Children under 16 pay $3.", ["$3"]),
    ("Where do I take old batteries?", "To the recycling center on Oak Street, open Tuesday to Saturday from 9am to 4pm.", ["oak street"]),
    ("Can plastic bags go in the blue bin?", "No. Plastic bags must not go in the blue bin.", ["not"]),
    ("Can I bring my dog to the pool?", "“I don’t know.” The guides do not mention dogs.", ["don't know"]),
]

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


# 9. Check one answer:
#    - if the expected answer starts with Yes or No, the first yes or no in the answer must be the same word
#    - it must not say "I don't know", unless that is the expected answer
#    - it must contain every key word
def passes(answer, expected, key_words):
    text = answer.lower().replace("\u2019", "'")
    expected_first_word = expected.split()[0].strip(".,").lower()
    if expected_first_word in ("yes", "no"):
        first_yes_or_no = re.search(r"\b(yes|no)\b", text)
        if not first_yes_or_no or first_yes_or_no.group(1) != expected_first_word:
            return False
    if "don't know" in text and "don't know" not in key_words:
        return False
    return all(word in text for word in key_words)


# 10. Ask every prepared question, check the answers, print the score and save the results
def evaluate(vector_store):
    results = []

    for number, (question, expected, key_words) in enumerate(QUESTIONS, start=1):
        found = search(vector_store, question)
        answer = ask_generate(build_prompt(found, question))
        passed = passes(answer, expected, key_words)

        print(f"[{number}/{len(QUESTIONS)}] {'PASS' if passed else 'FAIL'}  {question}")
        print(f"Expected: {expected}")
        print(f"Answer:   {answer}\n")

        results.append({
            "question": question,
            "expected": expected,
            "key_words": key_words,
            "answer": answer,
            "passed": passed,
            "chunks": [{"chunk_id": chunk.metadata["chunk_id"], "score": round(float(score), 2)}
                       for chunk, score in found],
        })

    passed_count = sum(result["passed"] for result in results)
    print(f"Passed {passed_count} of {len(results)}")

    # Save the settings and the results so two runs can be compared later
    report = {
        "chat_model": CHAT_MODEL,
        "embedding_model": EMBED_MODEL,
        "top_k": TOP_K,
        "passed": passed_count,
        "total": len(results),
        "results": results,
    }
    RESULTS_FOLDER.mkdir(exist_ok=True)
    output_file = RESULTS_FOLDER / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved the results to {output_file}")


# 11. Load or build the vector store, then run the evaluation
vector_store = load_or_build_vector_store()
evaluate(vector_store)

##-----------
# Results (two runs, saved in results/)
#
#   | Question                                       | TOP_K = 1 | TOP_K = 3 |
#   |------------------------------------------------|-----------|-----------|
#   | Can I drink water in a reading room?           | FAIL      | PASS      |
#   | Can a 15-year-old borrow a laptop?             | FAIL      | PASS (*)  |
#   | Can I take a library laptop home?              | FAIL      | PASS      |
#   | How often do I need to update my ... credentials? | PASS   | PASS      |
#   | Is the library open on Sundays?                | FAIL      | FAIL      |
#   | When is the pool closed for cleaning?          | PASS      | PASS      |
#   | How much does a single swim cost for a 12-year-old? | PASS | PASS      |
#   | Where do I take old batteries?                 | PASS      | PASS      |
#   | Can plastic bags go in the blue bin?           | FAIL      | PASS      |
#   | Can I bring my dog to the pool?                | FAIL      | PASS      |
#   | Score                                          | 4 of 10   | 9 of 10   |
#
# TOP_K = 3 did much better here. Examples of TOP_K = 1 failures:
# - Dog: only "Pool rules" was sent, and the model made up "No, ... everyone must shower ... dogs need to be bathed".
#   With 3 chunks it said "I don't know. There's no mention of dogs", which is right.
# - Plastic bags: "Yes, ... plastic bags do not go in the blue bin." The facts are right but it starts with the wrong word.
#
# (*) A false PASS. The answer was "... So, yes, a 15-year-old may borrow a laptop as long as they meet the
# age requirement of 18 or older". The check found "no" first (in "no mention of laptops") and found "18", so it passed.
# The real score for TOP_K = 3 is 8 of 10.

##-----------
# How the check works, and its limits
#
# passes() is a simple automatic check:
# - Yes or No: the first "yes" or "no" in the answer must match the expected answer.
# - It must not say "I don't know", unless that is the expected answer.
# - It must contain the key words, for example "$3" or "oak street".
#
# It is quick and free, but it only looks at words, not meaning. It can pass a wrong answer (the laptop one above)
# and fail a right one that is worded differently. So read the printed answers too, not only the score.
# A stronger check asks a second LLM to compare each answer with the expected one ("LLM as a judge").

##-----------
# How to use it
#
# 1. Run it once now. That is the baseline.
# 2. Change one thing: TOP_K, the instructions, the chunking, the model or the documents.
#    (After changing the documents or chunking, delete vector_store.json first.)
# 3. Run it again and compare the two files in results/.
# Small models are random, so a difference of one question can be luck. Run twice before trusting a change.
