"""
IT Knowledge Base: Chunking
===========================

Cuts the knowledge base's Documents into smaller pieces, chunks, so a search can find the part of an article that
matches. It handles:
  1. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  2. Keeping each chunk's article labels, plus start_index: where in the article's text it starts

Usage (this file only defines these; pipeline.py runs the steps):
    chunks = split_documents(docs)   ->  28 chunks of at most 512 characters, each with its article's labels
"""
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
