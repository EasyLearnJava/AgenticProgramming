"""
IT Knowledge Base, step 1: read the knowledge base, a CSV file of 10 IT support articles, into LangChain Documents.
No model, no API key.

    data/sample_it_kb.csv  ->  KBLoader(KB_FILE).load()  ->  docs, a list of 10 Documents: one per article

Run it in this folder:   python read_kb.py   ->   how many documents, every article's title, then the first
                                                  document's text and metadata

The data: 10 made-up IT support articles, copied unchanged from the course repo
https://github.com/Brianletort/KBs-For-RAGs (Clip1-v2/data/sample_it_kb.csv).
"""
import csv
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

# ① The file's path. Path(__file__).resolve().parent is the folder this script is in, and `/` on a Path adds a name
#    to it. A bare "data/sample_it_kb.csv" would be looked for in whatever folder you run the script from.
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"


# ② A LangChain document loader for the knowledge base. BaseLoader gives every loader the same methods: we write
#    lazy_load(), which hands out the Documents one at a time, and BaseLoader's load() collects them into a list.
class KBLoader(BaseLoader):
    def __init__(self, path: Path):
        self.path = path

    def lazy_load(self) -> Iterator[Document]:
        # newline="" is how the csv module wants a file opened. DictReader takes the column names from the first
        # line, then gives each line after it as a dict, {"title": ..., "problem": ..., ...}, skipping empty lines.
        with open(self.path, encoding="utf-8", newline="") as file:
            for number, row in enumerate(csv.DictReader(file)):
                # One Document per article. page_content is its text, one "column: value" line per column;
                # metadata says where it came from: the file's name and the row number, counted from 0.
                text = "\n".join(f"{column}: {value}" for column, value in row.items())
                yield Document(page_content=text, metadata={"source": self.path.name, "row": number})


# ③ The loader: it knows which file to read, but reads nothing yet.
loader = KBLoader(KB_FILE)

# ④ load() reads the file and gives back every Document in a list. This is the line that reads.
docs = loader.load()

# ⑤ Print what was read, but only when this file is run directly (python read_kb.py), not when the tests import it.
if __name__ == "__main__":
    print(f"{len(docs)} documents")
    for doc in docs:
        print(f"row {doc.metadata['row']}  {doc.page_content.splitlines()[0]}")   # the first line: the title
    print()

    first = docs[0]
    print(first.page_content)
    print()
    print(first.metadata)
