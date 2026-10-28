"""
IT Knowledge Base: Embeddings
=============================

The project's code in one file: it reads the IT knowledge base CSV file into LangChain Documents, cuts them into
chunks, then turns every chunk into a vector with Gemini: a list of numbers that stands for its meaning, so texts
with close meanings get vectors that point in close directions. It handles:
  1. Reading each article into a Document: its text in page_content, its labels in metadata
  2. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  3. Building Gemini's embedding model, after config.py has checked the API key: no key, no model
  4. Embedding every chunk's text in one call to Gemini
  5. Running the steps: main() names them, runs them, then prints the vectors with utils.py's print_vectors()

Building the model makes no call to Gemini: each embed_... does, and uses your key's quota.

Usage:
    python pipeline.py
"""
import csv
import sys
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import MissingKeyError, load_api_key
from utils import print_vectors

# Found next to this script, whichever folder it's run from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# The text is what gets searched and read; the labels are shown with an answer. The title is in both.
TEXT_COLUMNS = ["title", "problem", "resolution", "notes"]
METADATA_COLUMNS = ["title", "system", "category", "priority", "tags"]

# In characters: the articles are 569 to 716 characters long, so 512 makes 2 or 3 chunks each (28 in all)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# gemini-embedding-001 gives 128 to 3072 numbers per text; 768 is a size Google recommends, and cheaper to store
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768


class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores which file to read, and reads nothing
    Step 2: Load: lazy_load() reads the file, one Document per row (load() collects them into a list)
    """

    def __init__(self, path: Path = KB_FILE):
        self.path = path

    def lazy_load(self) -> Iterator[Document]:
        """Yield one Document per row: "Title: ..." blocks as the text, and the labels as metadata."""
        with open(self.path, encoding="utf-8", newline="") as file:
            # DictReader comes from Python's csv module: each row as {column: value}, named by the header row
            for number, row in enumerate(csv.DictReader(file)):
                # Each part keeps its label, so the model can tell the symptom from the fix
                text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
                metadata = {"doc_id": str(number), **{column: row[column] for column in METADATA_COLUMNS}}
                # Document comes from langchain_core: LangChain's text (page_content) with its labels (metadata)
                yield Document(page_content=text, metadata=metadata)


def load_documents(path: Path = KB_FILE) -> list[Document]:
    """Every article, as a list of Documents."""
    # load() comes from LangChain's BaseLoader, which KBLoader extends: lazy_load()'s Documents, in a list
    return KBLoader(path).load()


def make_splitter(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    """A splitter that breaks at empty lines first, then line breaks, then spaces; it records start_index."""
    # RecursiveCharacterTextSplitter comes from langchain_text_splitters: LangChain's splitter by size
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True)


def split_documents(docs: list[Document], chunk_size: int = CHUNK_SIZE,
                    chunk_overlap: int = CHUNK_OVERLAP) -> list[Document]:
    """Every Document cut into chunks, each a new Document with a copy of its article's metadata."""
    return make_splitter(chunk_size, chunk_overlap).split_documents(docs)


try:
    api_key = load_api_key()
except MissingKeyError as err:
    # exit() comes from Python's sys module: it stops the program with this message
    sys.exit(f"Can't build the models: {err}")

# embed_documents() embeds texts as documents to be found, embed_query() as a question looking for them
# GoogleGenerativeAIEmbeddings comes from langchain_google_genai: LangChain's class for Gemini's embeddings
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key,
                                          output_dimensionality=EMBEDDING_SIZE)


def embed_chunks(chunks: list[Document], embeddings: Embeddings) -> list[list[float]]:
    """One vector per chunk, from one embed_documents() call. Only the text is embedded, not the metadata."""
    # embed_documents() comes from LangChain's Embeddings (Gemini's, here): a list of texts in, a vector each out
    return embeddings.embed_documents([chunk.page_content for chunk in chunks])


# The tests pass a stand-in for Gemini as `embeddings`
def main(embeddings: Embeddings = embeddings) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    print("Step 3: Embed")
    vectors = embed_chunks(chunks, embeddings)
    print_vectors(chunks, vectors, EMBEDDING_MODEL)


if __name__ == "__main__":
    main()
