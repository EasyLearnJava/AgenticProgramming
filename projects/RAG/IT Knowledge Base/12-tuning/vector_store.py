"""
The vector database: Qdrant, holding one point per chunk: its vector, its text and its metadata. This is the last step
of getting the knowledge base ready to be searched (load, chunk, embed, store); the search, from a question, is in
retriever.py. From step 11 on, Qdrant can also run as a server (in Docker, see docker-compose.yml), which keeps its
points between runs, so the chunks are embedded only once.

    make_client()                                           ->  a client for the server at QDRANT_URL
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  an empty collection, "it_knowledge_base", in memory
    add_knowledge_base(store)                               ->  the 28 chunks embedded and stored   (one call to Gemini)

Run it on its own:   python vector_store.py   ->   the collection, then every point stored in it (Qdrant in memory)
"""
import os
import uuid

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from chunking import split_documents
from config import ENV_FILE
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings

# The collection's name (Qdrant's word for a table of points). Not the course app's "it_kb", so that the two apps
# never change each other's points on the same Qdrant server.
COLLECTION = "it_knowledge_base"

# The Qdrant server's address: from .env (or the environment), else the one docker-compose.yml opens on this machine.
load_dotenv(ENV_FILE)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")


# ① A client for the Qdrant server. Making it sends nothing: the first request does, and fails if no server answers.
#    check_compatibility=False skips qdrant-client's own check that the server's version matches the client's: it
#    runs in the background and only warns, and docker-compose.yml already pins the server to the client's version.
def make_client(url: str = QDRANT_URL) -> QdrantClient:
    return QdrantClient(url=url, check_compatibility=False)


# ② The store. A Qdrant client; a collection made for vectors of `size` numbers, compared by cosine similarity (how
#    closely two vectors point the same way, which step 06's search uses); and LangChain's QdrantVectorStore on top,
#    which embeds texts with `embeddings` for us. Without a client, QdrantClient(":memory:") runs Qdrant inside this
#    process, and everything in it is gone at the end.
def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    client = client if client is not None else QdrantClient(":memory:")
    if not client.collection_exists(collection):
        client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # QdrantVectorStore would check an existing collection by embedding a sample text: one more call to Gemini
    # each time a store is made. The collection was made here, with the right size, so that check is skipped.
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


# ③ A chunk's id, made from its article, its place and its text. The same chunk always gets the same id, so adding it
#    again replaces the stored point instead of adding a copy. Qdrant wants ids as UUIDs: uuid5 makes one from a text.
def chunk_id(chunk: Document) -> str:
    key = f"it-kb/{chunk.metadata['doc_id']}/{chunk.metadata['start_index']}/{chunk.page_content}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


# ④ Fill it: load the articles (step 02), cut them into chunks (step 03), and add the chunks with their ids.
#    add_documents() embeds every chunk's text, the same embed_documents() call as step 04 (one call to Gemini for all
#    of them), and stores each chunk as a point.
def add_knowledge_base(store: QdrantVectorStore) -> list[Document]:
    chunks = split_documents(load_documents())
    store.add_documents(chunks, ids=[chunk_id(chunk) for chunk in chunks])
    return chunks


if __name__ == "__main__":
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    # ⑤ What was stored: the collection's settings, then every point, read back from Qdrant. scroll() gives the points
    #    a page at a time (one page of up to 100 here: all 28), each with its vector and its payload, the chunk's text
    #    and metadata. They come back in id order, not the chunks' order, so they're sorted by article and place.
    params = store.client.get_collection(COLLECTION).config.params.vectors
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    points.sort(key=lambda point: (int(point.payload["metadata"]["doc_id"]), point.payload["metadata"]["start_index"]))
    print(f"Collection {COLLECTION!r}: {len(points)} points, vectors of {params.size} numbers, "
          f"compared by {params.distance.value}")
    print(f"Each point holds an id, a vector and a payload with {', '.join(sorted(points[0].payload))}")
    print()
    for number, point in enumerate(points, 1):
        metadata = point.payload["metadata"]
        print(f"Point {number} of {len(points)}: {metadata['title']}, from character {metadata['start_index']}: "
              f"{len(point.vector)} numbers, {len(point.payload['page_content'])} characters of text, "
              f"{len(metadata)} labels")
