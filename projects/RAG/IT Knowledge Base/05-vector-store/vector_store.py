"""
The vector database: Qdrant, here running inside this Python process ("in memory": no server, nothing to install),
holding one point per chunk: its vector, its text and its metadata. This is the last step of getting the knowledge
base ready to be searched (load, chunk, embed, store). There's no question here either: from step 06 on, a question
is embedded and Qdrant finds the chunks closest to it.

    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  an empty collection, "it_knowledge_base"
    add_knowledge_base(store)                               ->  the 28 chunks embedded and stored   (one call to Gemini)

Run it on its own:   python vector_store.py   ->   the collection, then every point stored in it
Optional: with QDRANT_URL set in .env and a Qdrant server running (docker compose up -d), the script stores the
chunks in that server instead of in memory, and Qdrant's dashboard shows them: http://localhost:6333/dashboard
"""
import os
import sys

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import Distance, VectorParams

from chunking import split_documents
from config import ENV_FILE
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings

# The collection's name (Qdrant's word for a table of points). Not the course app's "it_kb", so that the two apps
# never change each other's points on the same Qdrant server.
COLLECTION = "it_knowledge_base"

# The Qdrant server the script uses, if any: QDRANT_URL from .env (or the environment). Not set: Qdrant in memory.
load_dotenv(ENV_FILE)
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()


# ① The store. A Qdrant client; a collection made for vectors of `size` numbers, compared by cosine similarity (how
#    closely two vectors point the same way, which step 06's search uses); and LangChain's QdrantVectorStore on top,
#    which embeds texts with `embeddings` for us.
#    QdrantClient(":memory:") runs Qdrant inside this process, and everything in it is gone when the program ends.
def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    client = client if client is not None else QdrantClient(":memory:")
    if not client.collection_exists(collection):
        client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # QdrantVectorStore would check an existing collection by embedding a sample text: one more call to Gemini
    # each time a store is made. The collection was made here, with the right size, so that check is skipped.
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


# ② Fill it: load the articles (step 02), cut them into chunks (step 03), and add the chunks. add_documents() embeds
#    every chunk's text, the same embed_documents() call as step 04 (one call to Gemini for all of them), and stores
#    each chunk as a point: vector, text, metadata.
def add_knowledge_base(store: QdrantVectorStore) -> list[Document]:
    chunks = split_documents(load_documents())
    # add_documents() embeds and stores in one go. Inside LangChain it calls embeddings.embed_documents() on the
    # chunks' texts, the same method step 04's embed_chunks.py calls (one call to Gemini for all 28), then stores
    # each chunk as a point. This is how production code usually does it: hand the chunks to the vector store and
    # let it embed and store them, rather than embedding them yourself and building each point by hand.
    store.add_documents(chunks)
    return chunks


if __name__ == "__main__":
    # ③ Where Qdrant runs: in memory, or the server at QDRANT_URL when .env sets it. A server keeps its points
    #    between runs, and these points get random ids, so each run would add 28 more copies: the script deletes the
    #    collection first and stores the chunks again (step 11 reuses them instead). check_compatibility=False skips
    #    qdrant-client's background check of the server's version, which only warns.
    if QDRANT_URL:
        client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
        try:
            if client.collection_exists(COLLECTION):
                client.delete_collection(COLLECTION)
        except ResponseHandlingException:
            sys.exit(f"Can't reach Qdrant at {QDRANT_URL}. Start it first, in this folder: docker compose up -d "
                     "(or remove QDRANT_URL from .env to run Qdrant in memory).")
        print(f"Qdrant: the server at {QDRANT_URL}")
    else:
        client = QdrantClient(":memory:")
        print("Qdrant: in memory, inside this script")
    store = make_vector_store(embeddings, EMBEDDING_SIZE, client)
    add_knowledge_base(store)
    # ④ What was stored: the collection's settings, then every point, read back from Qdrant. scroll() gives the points
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
    if QDRANT_URL:
        print(f"\nSee them in Qdrant's dashboard: {QDRANT_URL.rstrip('/')}/dashboard")
        print("In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.")
