# Step 5: split the documents into chunks at each blank line, and print them.
# Next: 06_add_metadata.py

from pathlib import Path

# 1. Read the entire contents of every Markdown file in the docs folder
documents = []

for file in sorted(Path("docs").glob("*.md")):
    text = file.read_text(encoding="utf-8")
    if text.strip():
        documents.append(text)

if not documents:
    raise SystemExit(
        "No text found. Add Markdown files to the 'docs' folder."
    )

# 2. Split each document into chunks wherever there is a blank line
chunks = []

for document in documents:
    for paragraph in document.split("\n\n"):
        if paragraph.strip():
            chunks.append(paragraph.strip())

# 3. Print every chunk
for number, chunk in enumerate(chunks, start=1):
    print(f"Chunk {number} of {len(chunks)}")
    print(chunk)
    print()

print(f"Split {len(documents)} documents into {len(chunks)} chunks")

##-----------
# Chunking breaks each document into smaller parts, called chunks.
# Output: "Split 3 documents into 15 chunks". Each file gives 5 chunks: its title with the intro, then 4 sections.

##-----------
# There are different types of chunking, for example:
# - Fixed size: cut every N characters or tokens, wherever that falls.
# - Overlapping: fixed size, but each chunk repeats the end of the one before it,
#   so a sentence cut at the edge still appears whole in one of them.
# - By structure: cut at headings or paragraphs, as we do here.
# - By meaning: cut where the topic changes.
# We keep it simple here and cut at each blank line, which gives one chunk per section in our files.
