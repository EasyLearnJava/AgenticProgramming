"""
The knowledge base as LangChain Documents: data/sample_it_kb.csv, one Document per article. Each Document's text is
what gets searched and what the model reads (title, problem, resolution, notes); its metadata holds labels to show
with an answer and to filter by (system, category, priority, tags), plus the article's number and title.
No model, no API key.

    load_documents()  ->  10 Documents
        page_content:  "Title: VPN Connection Timeout\n\nProblem: ...\n\nResolution: ...\n\nNotes: ..."
        metadata:      {"doc_id": "0", "title": "VPN Connection Timeout", "system": "VPN", "category": "Remote Access",
                        "priority": "High", "tags": "vpn;timeout;remote;connection"}

Run it on its own:   python knowledge_base.py   ->   which columns went where, then every Document in full
"""
import csv
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

# ① The file, next to this script, found by its full path whichever folder you start from.
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# ② Which columns go where. TEXT_COLUMNS become the Document's text: what gets searched, and what the model reads.
#    METADATA_COLUMNS become labels kept next to the text: shown with an answer as its source, and usable as filters.
#    The title is in both: it helps the search, and it names the source.
TEXT_COLUMNS = ["title", "problem", "resolution", "notes"]
METADATA_COLUMNS = ["title", "system", "category", "priority", "tags"]


# ③ The loader: one Document per line of the file (empty lines are skipped), with the text and the metadata
#    kept apart.
class KBLoader(BaseLoader):
    def __init__(self, path: Path = KB_FILE):
        self.path = path

    def lazy_load(self) -> Iterator[Document]:
        with open(self.path, encoding="utf-8", newline="") as file:
            for number, row in enumerate(csv.DictReader(file)):
                # "Title: ...", "Problem: ..." and so on, with an empty line between them: the labels tell the model
                # which part is the symptom and which is the fix.
                text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
                metadata = {"doc_id": str(number), **{column: row[column] for column in METADATA_COLUMNS}}
                yield Document(page_content=text, metadata=metadata)


# ④ Every article, as a list of Documents.
def load_documents(path: Path = KB_FILE) -> list[Document]:
    return KBLoader(path).load()


if __name__ == "__main__":
    docs = load_documents()
    # ⑤ What went where, then every Document in full, with a note before each part.
    print(f"{len(docs)} documents")
    print("text:     " + ", ".join(TEXT_COLUMNS))
    print("metadata: " + ", ".join(["doc_id", *METADATA_COLUMNS]))
    print()
    for number, doc in enumerate(docs):
        if number > 0:
            print()                                   # a blank line between documents, not before the first one
        print(f"Document {number + 1} of {len(docs)}")
        print("Text (page_content):")
        print(doc.page_content)
        print()
        print("Labels (metadata):")
        print(doc.metadata)
