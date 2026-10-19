"""
Embeddings: the knowledge base's 28 chunks turned into vectors by Gemini. A vector is a list of numbers that stands for
a text's meaning: texts with close meanings get vectors that point in close directions. This is the third step of
getting the knowledge base ready to be searched (load, chunk, embed); step 05 stores the vectors, and from step 06 on
a user's question is embedded too and compared with them. There's no question here: only the chunks are embedded.

    embed_chunks(split_documents(load_documents()), embeddings)
        ->  28 vectors of 768 numbers, one per chunk, in the chunks' order   (one call to Gemini for all 28)

Run it on its own:   python embed_chunks.py   ->   every chunk with its vector's size and first numbers
"""
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_MODEL, embeddings


# ① Embed every chunk's text in one call. embed_documents() tells Gemini the texts are documents to be found
#    (RETRIEVAL_DOCUMENT). Only the text (page_content) is sent: the labels in metadata aren't embedded.
def embed_chunks(chunks: list[Document], embeddings: Embeddings) -> list[list[float]]:
    return embeddings.embed_documents([chunk.page_content for chunk in chunks])


if __name__ == "__main__":
    chunks = split_documents(load_documents())
    # ② The one call to Gemini: 28 texts in, 28 vectors out, in the same order as the chunks.
    vectors = embed_chunks(chunks, embeddings)
    # ③ Every chunk with its vector: its article and which characters of the article's text it holds (from start_index
    #    to start_index + its length), then how many numbers it was converted to, and the first 5 of them.
    print(f"{len(chunks)} chunks -> {len(vectors)} vectors ({EMBEDDING_MODEL})")
    print()
    for number, (chunk, vector) in enumerate(zip(chunks, vectors), 1):
        start = chunk.metadata["start_index"]
        end = start + len(chunk.page_content)
        first = ", ".join(f"{x:.4f}" for x in vector[:5])
        print(f"Chunk {number} of {len(chunks)}: {chunk.metadata['title']}, from character {start} to {end} "
              f"-> converted to {len(vector)} numbers: [{first}, ...]")
