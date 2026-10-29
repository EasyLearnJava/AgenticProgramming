"""
IT Knowledge Base: Chunking
===========================

Cuts each article into chunks small enough to search well, and gives every chunk an ID that stays the same from run
to run, so a log line, a search hit and a stored point can all name the same chunk. It handles:
  1. Splitting at empty lines first (between an article's sections), then line breaks, then spaces, to at most
     chunk_size characters, with chunk_overlap characters shared between neighbours
  2. Each chunk's place: its article's metadata, where in the article it starts (start_index), its position among
     its article's chunks (chunk_index), and its ID (chunk_id)

    chunk_id = a UUID made from the file, the article, where the chunk starts and a hash of its text: the same
               chunk always gets the same ID, and a changed chunk a new one

Usage:
    chunker = Chunker(chunk_size=512, chunk_overlap=50)
    chunks = chunker.split(documents)     ->  the chunks, in order, each a Document
"""
import hashlib
import uuid
from collections import Counter

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.observability.tracing import span


class Chunker:
    """
    Splits Documents into chunks, each with a stable chunk_id.

    Step 1: Configure: the constructor stores the sizes and makes the splitter
    Step 2: Split: split() cuts every Document and labels each chunk
    """

    def __init__(self, *, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                                        add_start_index=True)

    def split(self, documents: list[Document]) -> list[Document]:
        """Every Document cut into chunks, each a new Document with a copy of its article's metadata and its own
        start_index, chunk_index and chunk_id."""
        with span("chunking.split", documents=len(documents), chunk_size=self.chunk_size) as fields:
            chunks = self._splitter.split_documents(documents)
            per_article: Counter[str] = Counter()
            for chunk in chunks:
                doc_id = chunk.metadata["doc_id"]
                chunk.metadata["chunk_index"] = per_article[doc_id]
                chunk.metadata["chunk_id"] = chunk_id(chunk)
                per_article[doc_id] += 1
            lengths = [len(chunk.page_content) for chunk in chunks]
            fields.update(chunks=len(chunks), min_chars=min(lengths, default=0), max_chars=max(lengths, default=0))
            return chunks


def chunk_id(chunk: Document) -> str:
    """A UUID for the chunk, the same every run for the same text at the same place in the same article."""
    text_hash = hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()[:16]
    key = f"{chunk.metadata['source']}|{chunk.metadata['doc_id']}|{chunk.metadata['start_index']}|{text_hash}"
    # uuid5 is a UUID made from a name: Qdrant takes it as the point's ID
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"it-knowledge-base:{key}"))
