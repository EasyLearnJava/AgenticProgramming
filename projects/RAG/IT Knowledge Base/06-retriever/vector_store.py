"""
The vector database: Qdrant, here running inside this Python process ("in memory": no server, nothing to install),
holding one point per chunk: its vector, its text and its metadata. A search embeds the question and returns the
chunks whose vectors are closest.

    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  an empty collection, "it_knowledge_base"
    add_knowledge_base(store)                               ->  the 28 chunks embedded and stored   (one call to Gemini)
    store.similarity_search_with_score("My VPN won't connect", k=5)
                                                            ->  [(chunk, 0.81), ...], closest first  (one call)

Run it on its own:   python vector_store.py                  ->   the 5 chunks closest to "My VPN won't connect"
                     python vector_store.py "lost printer"   ->   the 5 closest to your question
"""
import sys

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings

# The collection's name (Qdrant's word for a table of points). Not the course app's "it_kb", so that the two apps
# never change each other's points on the same Qdrant server.
COLLECTION = "it_knowledge_base"
QUESTION = "My VPN won't connect"


# ① The store. A Qdrant client; a collection made for vectors of `size` numbers, compared by cosine similarity (step
#    04's measure); and LangChain's QdrantVectorStore on top, which embeds texts with `embeddings` for us.
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
#    every chunk's text (one call to Gemini for all of them) and stores each chunk as a point: vector, text, metadata.
def add_knowledge_base(store: QdrantVectorStore) -> list[Document]:
    chunks = split_documents(load_documents())
    store.add_documents(chunks)
    return chunks


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or QUESTION
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    chunks = add_knowledge_base(store)
    print(f"{len(chunks)} chunks stored in the collection {COLLECTION!r}")
    # ③ Search: embed the question (one call), and get the 5 closest chunks with their scores, closest first.
    #    The score is the cosine similarity: the closer to 1, the closer the meaning.
    print(f"\nThe 5 chunks closest to {question!r}:")
    for chunk, score in store.similarity_search_with_score(question, k=5):
        print(f"  {score:.3f}  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
