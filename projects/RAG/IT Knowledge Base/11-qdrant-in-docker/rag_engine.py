"""
The RAG engine: steps 02 to 07 in one class, the way a server uses them. build() fills the vector store, and query()
then answers each question with its sources. From step 11 on, the vector store is a Qdrant server that keeps its
points between runs: build() embeds the chunks only when the server doesn't already hold exactly these chunks.

    engine = RAGEngine()       settings only: nothing read, no call yet; the Qdrant server at QDRANT_URL
    engine.build()         ->  10 articles, 28 chunks: embedded and stored the first time (one call to Gemini),
                               found already stored after that (no call)
    engine.query("How do I fix VPN connection timeouts?")
        ->  {"answer": "...", "sources": [{"title": "VPN Connection Timeout", "system": "VPN",
                                           "category": "Remote Access", "snippet": "Title: VPN Connection ..."}, ...]}
                                                                                         (two calls: embedding, answer)
    engine.stats()         ->  {"documents": 10, "chunks": 28, "reused_stored_chunks": True, ...}

Run it on its own:   python rag_engine.py                       ->   answers to the three sample questions
                     python rag_engine.py "printer not found"   ->   the answer to your question
The Qdrant server must be running first:   docker compose up -d
"""
import sys

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from qdrant_client import QdrantClient

from chunking import CHUNK_OVERLAP, CHUNK_SIZE, split_documents
from knowledge_base import load_documents
from models import CHAT_MODEL, EMBEDDING_MODEL, EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain
from retriever import QUESTIONS, TOP_K, make_retriever
from vector_store import COLLECTION, QDRANT_URL, chunk_id, make_client, make_vector_store

MAX_SOURCES = 3        # sources per answer: the first 3 different articles among the chunks found
SNIPPET_LENGTH = 200   # characters of each source's text shown with it


class RAGEngine:
    # ① Settings only: no file is read and no call is made until build(). Without a client, build() connects to the
    #    Qdrant server at QDRANT_URL. The models, the client and the sizes can be swapped, as the tests do.
    def __init__(self, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
                 embedding_size: int = EMBEDDING_SIZE, client: QdrantClient | None = None,
                 chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, top_k: int = TOP_K):
        self.embeddings, self.model, self.embedding_size = embeddings, model, embedding_size
        self.client = client
        self.chunk_size, self.chunk_overlap, self.top_k = chunk_size, chunk_overlap, top_k
        self.documents, self.chunks = [], []
        self.reused_stored_chunks = False
        self.chain: Runnable | None = None

    # ② Build: load and split the articles, and make sure the server holds exactly these chunks, then make the chain.
    #    Each chunk's id is made from its text (step 11's chunk_id), so "these chunks" can be checked by id:
    #    - all of them stored, and nothing else:  reuse them, no call to Gemini;
    #    - anything else (an edited article, other sizes):  empty the collection, then store them anew;
    #    - no collection yet (the first run):  store them.
    def build(self) -> None:
        if self.client is None:
            self.client = make_client()
        self.documents = load_documents()
        self.chunks = split_documents(self.documents, self.chunk_size, self.chunk_overlap)
        ids = [chunk_id(chunk) for chunk in self.chunks]
        self.reused_stored_chunks = False
        if self.client.collection_exists(COLLECTION):
            stored = self.client.count(COLLECTION).count
            found = len(self.client.retrieve(COLLECTION, ids=ids, with_payload=False, with_vectors=False))
            self.reused_stored_chunks = stored == found == len(ids)
            if not self.reused_stored_chunks:
                self.client.delete_collection(COLLECTION)
        store = make_vector_store(self.embeddings, self.embedding_size, self.client)
        if not self.reused_stored_chunks:
            store.add_documents(self.chunks, ids=ids)          # one call to Gemini: every chunk's embedding
        self.chain = make_rag_chain(make_retriever(store, self.top_k), self.model)

    # ③ One question: run the chain, then keep the answer and turn the chunks it found into sources.
    def query(self, question: str) -> dict:
        return self._with_sources(self._built_chain().invoke(question))

    # ④ The same for async code, such as a FastAPI route: while Gemini works, the server can do other work.
    async def aquery(self, question: str) -> dict:
        return self._with_sources(await self._built_chain().ainvoke(question))

    def _built_chain(self) -> Runnable:
        if self.chain is None:
            raise RuntimeError("The engine isn't built yet: call build() first.")
        return self.chain

    # ⑤ The sources: the first MAX_SOURCES different articles among the chunks, closest first, each with the start of
    #    the chunk's text. Two chunks of one article give one source.
    @staticmethod
    def _with_sources(result: dict) -> dict:
        sources, seen = [], set()
        for doc in result["docs"]:
            if doc.metadata["doc_id"] in seen:
                continue
            seen.add(doc.metadata["doc_id"])
            text = doc.page_content
            snippet = text[:SNIPPET_LENGTH] + ("..." if len(text) > SNIPPET_LENGTH else "")
            sources.append({key: doc.metadata[key] for key in ("title", "system", "category")} | {"snippet": snippet})
            if len(sources) == MAX_SOURCES:
                break
        return {"answer": result["answer"], "sources": sources}

    # ⑥ What the engine holds and how it's set up, including whether build() found the chunks already stored.
    def stats(self) -> dict:
        return {"documents": len(self.documents), "chunks": len(self.chunks), "collection": COLLECTION,
                "chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap, "top_k": self.top_k,
                "embedding_model": EMBEDDING_MODEL, "chat_model": CHAT_MODEL,
                "reused_stored_chunks": self.reused_stored_chunks}


if __name__ == "__main__":
    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS
    engine = RAGEngine()
    engine.build()
    stats = engine.stats()
    how = "already stored, reused" if stats["reused_stored_chunks"] else "embedded and stored"
    print(f"Built: {stats['documents']} articles, {stats['chunks']} chunks ({how}) in Qdrant at {QDRANT_URL}\n")
    for question in questions:
        result = engine.query(question)
        print(f"Q: {question}\nA: {result['answer']}")
        for source in result["sources"]:
            print(f"   source: {source['title']} ({source['system']}, {source['category']})")
        print()
