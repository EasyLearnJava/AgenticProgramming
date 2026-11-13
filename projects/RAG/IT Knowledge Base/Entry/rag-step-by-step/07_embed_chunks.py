# Step 7: turn each chunk into a vector, a list of numbers that captures its meaning.
# Next: 08_search_by_meaning.py

import numpy as np
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from pathlib import Path

# 1. Settings
OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

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
documents = {}

for file in sorted(Path("docs").glob("*.md")):
    text = file.read_text(encoding="utf-8")
    if text.strip():
        documents[file.name] = text

if not documents:
    raise SystemExit(
        "No text found. Add Markdown files to the 'docs' folder."
    )

# 3. Split each document into chunks wherever there is a blank line, and label each chunk
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

        # Document comes from LangChain: the text (page_content) with its labels (metadata)
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

# 4. Turn every chunk's text into a vector, in one call to the embedding model
vectors = embedding_model.embed_documents([chunk.page_content for chunk in chunks])

# 5. Print every chunk: its text, then its vector
for number, (chunk, vector) in enumerate(zip(chunks, vectors), start=1):
    print(f"Chunk {number} of {len(chunks)} ({chunk.metadata['chunk_id']})")
    print("Text:")
    print(chunk.page_content)
    print(f"Vector: {len(vector)} numbers. The first 8:")
    print([round(value, 4) for value in vector[:8]])
    print(f"Length: {np.linalg.norm(vector)}")  # square every number, add them up, take the square root
    #print(vector)  # uncomment to see all the numbers
    print()

print(f"Turned {len(chunks)} chunks into {len(vectors)} vectors of {len(vectors[0])} numbers each")

# 6. Print the complete vector of one chunk: all its numbers, not rounded
chunk_number = 2  # which chunk to show, from 1 to the number of chunks
print(f"\nComplete vector of chunk {chunk_number} ({chunks[chunk_number - 1].metadata['chunk_id']}):")
print(vectors[chunk_number - 1])

# =====================================================================================================
# NOTES
# 1. The output
# 2. What a vector is
# 3. The length of a vector
# 4. How two vectors are compared: the cosine formula
# 5. Cosine or dot product: why the length matters
# 6. How to choose cosine or dot product
# 7. What vector databases support
# =====================================================================================================

##-----------
# 1. The output (two of the 15 chunks)
#
#   Chunk 2 of 15 (handbook.md#1)
#   ## Opening hours
#   The library is open from 9am to 8pm Monday through Thursday ...
#   Vector: 768 numbers. The first 8:
#   [-0.0474, -0.0004, -0.1473, -0.0563, 0.0208, 0.0171, -0.0105, -0.0463]
#   Length: 1.0000002611700685
#
#   Chunk 14 of 15 (swimming_pool.md#3)
#   ## Children
#   Children under 10 must be watched by an adult in the water at all times. ...
#   Vector: 768 numbers. The first 8:
#   [-0.0244, 0.0278, -0.1931, -0.0301, 0.0162, 0.1249, 0.0668, -0.0031]
#   Length: 1.0000004849995097
#
#   Turned 15 chunks into 15 vectors of 768 numbers each
#
# Every chunk, long or short, becomes exactly 768 numbers. nomic-embed-text always gives 768.

##-----------
# 2. What a vector is
#
# Think of a vector as an arrow:
# - Its direction is the meaning.
# - Its length says nothing about the meaning.
#
# One number means nothing on its own. The third number is between -0.14 and -0.21 in all 15 chunks,
# whether the chunk is about library hours, children at the pool or batteries.
# The meaning is in all 768 numbers together: chunks about similar things point in similar directions.
#
# Only page_content is turned into a vector, not the labels. Chunk 14's vector comes from
# "## Children ..." alone, so it carries nothing about "pool", even though its title label says
# "Mapleford Community Pool Guide".
#
# The same text always gives the same vector, so a chunk only needs embedding once, until its text changes.

##-----------
# 3. The length of a vector
#
# length = square every number, add them up, take the square root
# The loop above prints it for every chunk: np.linalg.norm(vector)
#
# Measured here: all 15 lengths are between 0.9999995 and 1.0000005, so every vector has length 1.
# The tiny difference from exactly 1 is rounding, because each number is stored with about 8 digits.
# Not every embedding model does this. Some return vectors of any length.
# Check a few vectors, not just one. The model's documentation usually says too ("normalized" or "unit length").
#
# To make a vector length 1 yourself (normalize it), divide it by its length:
#   vector = np.array(vector) / np.linalg.norm(vector)

##-----------
# 4. How two vectors are compared: the cosine formula
#
#   cosine      = dot product / (length of question x length of chunk)
#   dot product = multiply the numbers at the same position, then add all the results
#
# Example 1: small made-up vectors with 3 numbers, to follow by hand
#
#   | Vector   | Numbers     | Length                    |
#   |----------|-------------|---------------------------|
#   | Question | [1, 2, 2]   | sqrt(1+4+4) = sqrt(9) = 3 |
#   | Chunk A  | [2, 1, 2]   | sqrt(4+1+4) = sqrt(9) = 3 |
#   | Chunk B  | [2, -2, 1]  | sqrt(4+4+1) = sqrt(9) = 3 |
#
#   Question and A: dot = 1x2 + 2x1 + 2x2    = 2 + 2 + 4 = 8   cosine = 8 / (3 x 3) = 0.89  very similar
#   Question and B: dot = 1x2 + 2x(-2) + 2x1 = 2 - 4 + 2 = 0   cosine = 0 / (3 x 3) = 0     not related
#
# Example 2: the real vectors for "Where do I take old batteries?" and chunk 9 "Batteries and electronics"
#
#   | Position         | Question | Chunk 9 | Multiplied |
#   |------------------|----------|---------|------------|
#   | 1                |  0.0018  | -0.0182 |  -0.0000   |
#   | 2                |  0.0011  |  0.0528 |   0.0001   |
#   | 3                | -0.1805  | -0.1730 |   0.0312   |
#   | ...              |   ...    |   ...   |    ...     |
#   | all 768 added up |          |         |   0.6006   |
#
#   Both lengths are 1, so cosine = 0.6006 / (1 x 1) = 0.60
#   Chunk 15 "Pool rules" goes through the same steps with its own 768 numbers and gets 0.48.
#
# Same sign at a position (both + or both -) gives a positive product and pushes the score up.
# Opposite signs pull it down. The score runs from 1 (same meaning) through 0 (unrelated) to -1 (opposite).
#
# In NumPy the whole formula is one line:
#   score = chunk_vector @ question_vector / (np.linalg.norm(chunk_vector) * np.linalg.norm(question_vector))

##-----------
# 5. Cosine or dot product: why the length matters
#
# - Cosine looks only at the direction: do the two arrows point the same way?
# - Dot product is direction match x length.
#
# Why it matters: it depends on how you compare vectors.
# - Cosine similarity divides by both lengths, so the length doesn't matter. 
#   so it's safe with any model.
# - Dot product is faster, and many vector databases use it. It gives the same result as cosine only when every
#   vector has length 1. With vectors that aren't normalized, longer vectors score higher just for being long.
#   If your database uses dot product, normalize first: divide each vector by its length.
#
# Example: "Where do I take old batteries?" against two chunks
#
#   As the vectors come (length 1), both ways agree and Batteries wins. Correct.
#
#   | Chunk                        | Cosine | Length | Dot product (match x length) |
#   |------------------------------|--------|--------|------------------------------|
#   | 9. Batteries and electronics |  0.60  |   1    | 0.60 x 1 = 0.60              |
#   | 15. Pool rules               |  0.48  |   1    | 0.48 x 1 = 0.48              |
#
#   Now, as an experiment, make the arrows longer without changing their direction (their meaning):
#   chunk 9 is multiplied by 9 and chunk 15 by 15.
#
#   | Chunk                        | Cosine     | Length | Dot product (match x length) |
#   |------------------------------|------------|--------|------------------------------|
#   | 9. Batteries and electronics | still 0.60 |   9    | 0.60 x 9  = 5.41             |
#   | 15. Pool rules               | still 0.48 |   15   | 0.48 x 15 = 7.24             |
#
#   Cosine ignores the length, so Batteries still wins. Correct.
#   Dot product now picks Pool rules, a worse match, only because its arrow is longer. Wrong.
#
# Like a singing contest: cosine judges how well each person sings. Dot product judges how well they sing
# times how loud they are. If everyone sings at the same volume (length 1), both judges pick the same winner.
# If one singer turns up the microphone, the dot product judge picks the loudest, not the best.
#
# Our vectors already have length 1, so this cannot happen with them. The stretch was only an experiment.

##-----------
# 6. How to choose cosine or dot product
#
# - Use what the embedding model was trained for. Its model card or documentation says which, for example
#   "similarity: cosine". Most models are trained for cosine. A few are trained for dot product and should be
#   compared with dot product, without normalizing.
# - If the vectors have length 1, both give the same ranking. Dot product is then the cheaper choice.
# - If you're not sure, use cosine. It gives the right ranking whether or not the vectors have length 1.

##-----------
# 7. What vector databases support
#
# Check the database's documentation for "distance" or "metric". Most let you choose when you create the
# collection or index, and it can't be changed afterwards.
#
#   | Database   | Options                                   | Watch for                                     |
#   |------------|-------------------------------------------|-----------------------------------------------|
#   | Qdrant     | Cosine, Dot, Euclid, Manhattan            | With Cosine it normalizes the vectors when    |
#   |            |                                           | they are stored, then uses dot product        |
#   | pgvector   | <=> cosine, <#> dot, <-> Euclidean        | Build the index for the same one              |
#   |            |                                           | (vector_cosine_ops, vector_ip_ops,            |
#   |            |                                           | vector_l2_ops), or the query won't use it     |
#   | Chroma     | cosine, ip (dot), l2 (Euclidean)          | The default is l2, so set it                  |
#   | Pinecone   | cosine, dotproduct, euclidean             | Chosen when the index is created              |
#   | FAISS      | IndexFlatIP (dot), IndexFlatL2 (Euclidean)| For cosine, normalize first, use IndexFlatIP  |
#
# With length-1 vectors, Euclidean distance also gives the same ranking as cosine, so any of the three works.
