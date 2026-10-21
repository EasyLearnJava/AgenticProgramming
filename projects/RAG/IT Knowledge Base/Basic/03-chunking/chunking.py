"""
IT Knowledge Base: Chunking
===========================

Cuts the knowledge base's Documents into smaller pieces, chunks, so a search can find the part of an article that
matches. It handles:
  1. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  2. Keeping each chunk's article labels, plus start_index: where in the article's text it starts
  3. Printing how many chunks each article makes, then every chunk

Usage:
    python chunking.py        # how many chunks each article makes, then every article's chunks
    python chunking.py 200    # the same, with chunks of at most 200 characters
"""
import sys

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from knowledge_base import load_documents

# In characters: the articles are 569 to 716 characters long, so 512 makes 2 or 3 chunks each (28 in all)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


def make_splitter(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    """A splitter that breaks at empty lines first, then line breaks, then spaces; it records start_index."""
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True)


def split_documents(docs: list[Document], chunk_size: int = CHUNK_SIZE,
                    chunk_overlap: int = CHUNK_OVERLAP) -> list[Document]:
    """Every Document cut into chunks, each a new Document with a copy of its article's metadata."""
    return make_splitter(chunk_size, chunk_overlap).split_documents(docs)


if __name__ == "__main__":
    size = int(sys.argv[1]) if len(sys.argv) > 1 else CHUNK_SIZE
    docs = load_documents()
    chunks = split_documents(docs, chunk_size=size)
    print(f"{len(docs)} articles -> {len(chunks)} chunks of at most {size} characters")
    for doc in docs:
        count = sum(chunk.metadata["doc_id"] == doc.metadata["doc_id"] for chunk in chunks)
        print(f"  {count} from {doc.metadata['title']} ({len(doc.page_content)} characters)")
    for number, doc in enumerate(docs):
        mine = [chunk for chunk in chunks if chunk.metadata["doc_id"] == doc.metadata["doc_id"]]
        print()
        print(f"Article {number + 1} of {len(docs)}: {doc.metadata['title']}, "
              f"cut into {len(mine)} chunk{'s' if len(mine) > 1 else ''}")
        for place, chunk in enumerate(mine, 1):
            print()
            print(f"Chunk {place} of {len(mine)}, from character {chunk.metadata['start_index']} "
                  f"({len(chunk.page_content)} characters):")
            print(chunk.page_content)
