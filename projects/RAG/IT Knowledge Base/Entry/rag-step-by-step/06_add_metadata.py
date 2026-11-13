# Step 6: give each chunk labels (metadata) that say where it came from and who may see it.
# Next: 07_embed_chunks.py

from langchain_core.documents import Document
from pathlib import Path

# 1. Settings
# Who looks after each document (example values for our sample files)
DOCUMENT_OWNERS = {
    "handbook.md": "Library team",
    "recycling.md": "Waste services team",
    "swimming_pool.md": "Pool team",
}

# Who may see the documents. For now every document is open to everyone.
ACCESS = "everyone"

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

# 4. Print every chunk: its text, then its labels
for number, chunk in enumerate(chunks, start=1):
    print(f"Chunk {number} of {len(chunks)}")
    print("Text (page_content):")
    print(chunk.page_content)
    print("Labels (metadata):")
    print(chunk.metadata)
    print()

print(f"Split {len(documents)} documents into {len(chunks)} labelled chunks")

##-----------
# Output for chunk 14:
#   Text (page_content):
#   ## Children
#   Children under 10 must be watched by an adult in the water at all times. ...
#   Labels (metadata):
#   {'source': 'swimming_pool.md', 'title': 'Mapleford Community Pool Guide', 'section': 'Children',
#    'chunk_id': 'swimming_pool.md#3', 'owner': 'Pool team', 'access': 'everyone'}
#
# In step 5 this chunk never said "pool", so it could have come from any guide.
# Its labels now say where it came from: the file, the guide's title and the section.

##-----------
# What each label is used for (the values are chunk 14's)
#
# source = 'swimming_pool.md'
#   - Shows which file an answer came from.
#   - When the file changes, find all of its chunks and replace them.
#   - Search one file only, for example only the pool guide.
#
# title = 'Mapleford Community Pool Guide'
#   - A readable name to show people instead of the file name.
#   - Can be added in front of the chunk's text, so "## Children ..." also says which guide it is from.
#
# section = 'Children'
#   - Points to the exact part of the guide, so a person can check the answer.
#     Together with the title: "Mapleford Community Pool Guide > Children".
#
# chunk_id = 'swimming_pool.md#3'
#   - A unique name for this one chunk: the file, then its position counting from 0 (#3 is the 4th chunk).
#   - Update or delete this one chunk without touching the others.
#   - Store its vector under this name, so the chunk doesn't need embedding again.
#   - Record which chunks were used for each answer.
#
# owner = 'Pool team'
#   - Who to ask when the text is wrong or out of date. If the swim test rule changes, the Pool team updates it.
#   - Comes from DOCUMENT_OWNERS: the code looks up "swimming_pool.md" and finds "Pool team".
#     A file missing from that table, such as a new parking.md, gets "unknown".
#   - In a real system the owner comes from where the document is stored (SharePoint, Confluence, the author),
#     not from a table in the code. The table stands in for that here.
#   - Uses: send reports of wrong answers to the right team, remind owners to review old documents,
#     and pass on questions the documents can't answer (such as dogs at the pool).
#   - Here it is only printed. Nothing reads it yet.
#
# access = 'everyone'
#   - Who may see the chunk. Chunks a user may not see are removed before anything reaches the model.
#   - Every chunk is "everyone" here. A staff-only document would get another value, such as "staff".
#
# Example: an answer that uses these labels could end with
#   Source: Mapleford Community Pool Guide > Children (swimming_pool.md#3)
#
# The labels sit next to the text. They are not part of it, so the model only sees them if we put them in the prompt.
#
# sorted() reads the files in name order on every machine, so the chunk numbers and chunk_ids stay the same.
