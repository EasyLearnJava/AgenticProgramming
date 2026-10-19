"""
Chunking: the knowledge base's Documents cut into smaller pieces, chunks. From step 04 on, chunks are what gets
embedded, stored and searched, so a search finds the part of an article that matches, not just the article.
No model, no API key.

    split_documents(load_documents())  ->  chunks: Documents of at most CHUNK_SIZE characters, each with its
                                           article's metadata plus start_index, where in the article's text it starts

Run it on its own:   python chunking.py        ->   how many chunks each article makes, then every article's chunks
                     python chunking.py 200    ->   the same, with chunks of at most 200 characters
"""
import sys

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from knowledge_base import load_documents

# ① The sizes, in characters. The articles' texts are 569 to 716 characters long, so 512 cuts each one into 2 or 3
#    chunks: 28 in all. The overlap lets the end of a chunk be repeated at the start of the next one (up to 50
#    characters), so a sentence cut at the edge can still be whole in one of them.
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


# ② The splitter. "Recursive" means it tries the biggest breaks first: an empty line (between Title, Problem,
#    Resolution and Notes), then a line break, then a space, and only cuts inside a word if nothing else fits.
#    add_start_index=True adds start_index to each chunk's metadata.
def make_splitter(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True)


# ③ Split every Document. Each chunk is a new Document with a copy of its article's metadata.
def split_documents(docs: list[Document], chunk_size: int = CHUNK_SIZE,
                    chunk_overlap: int = CHUNK_OVERLAP) -> list[Document]:
    return make_splitter(chunk_size, chunk_overlap).split_documents(docs)


if __name__ == "__main__":
    size = int(sys.argv[1]) if len(sys.argv) > 1 else CHUNK_SIZE
    docs = load_documents()
    chunks = split_documents(docs, chunk_size=size)
    # ④ How many chunks each article made, then every article's chunks, each with where it starts and its length.
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
            print()                                   # a blank line before each chunk
            print(f"Chunk {place} of {len(mine)}, from character {chunk.metadata['start_index']} "
                  f"({len(chunk.page_content)} characters):")
            print(chunk.page_content)
