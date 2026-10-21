"""
The RAG engine: steps 02 to 07 in one class, the way a server uses them. build() fills the vector store once, and
query() then answers each question with its sources.

    engine = RAGEngine()       settings only: nothing read, no call yet
    engine.build()         ->  10 articles, 28 chunks embedded and stored               (one call to Gemini)
    engine.query("How do I fix VPN connection timeouts?")
        ->  {"answer": "...", "sources": [{"title": "VPN Connection Timeout", "system": "VPN",
                                           "category": "Remote Access", "snippet": "Title: VPN Connection ..."}, ...]}
                                                                                         (two calls: embedding, answer)
    engine.stats()         ->  {"documents": 10, "chunks": 28, "chunk_size": 512, ...}

Run it on its own:   python rag_engine.py                       ->   answers to the three sample questions
                     python rag_engine.py "printer not found"   ->   the answer to your question
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
from vector_store import COLLECTION, make_vector_store

MAX_SOURCES = 3        # sources per answer: the first 3 different articles among the chunks found
SNIPPET_LENGTH = 200   # characters of each source's text shown with it


class RAGEngine:
    # ① Settings only: no file is read and no call is made until build(). The models, the Qdrant client and the
    #    sizes can be swapped, as the tests do (with stand-ins for Gemini) and step 12 does (other sizes).
    def __init__(self, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
                 embedding_size: int = EMBEDDING_SIZE, client: QdrantClient | None = None,
                 chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, top_k: int = TOP_K):
        self.embeddings, self.model, self.embedding_size, self.client = embeddings, model, embedding_size, client
        self.chunk_size, self.chunk_overlap, self.top_k = chunk_size, chunk_overlap, top_k
        self.documents, self.chunks = [], []
        self.chain: Runnable | None = None

    # ② Build once: load and split the articles (steps 02 and 03), embed and store the chunks (04 and 05), and make
    #    the chain (06 and 07). This is where the chunks' embeddings are made: one call to Gemini.
    def build(self) -> None:
        self.documents = load_documents()
        self.chunks = split_documents(self.documents, self.chunk_size, self.chunk_overlap)
        store = make_vector_store(self.embeddings, self.embedding_size, self.client)
        store.add_documents(self.chunks)
        self.chain = make_rag_chain(make_retriever(store, self.top_k), self.model)

    # ③ One question: run the chain, then keep the answer and turn the chunks it found into sources.
    def query(self, question: str) -> dict:
        return self._with_sources(self._built_chain().invoke(question))

    # ④ The same for async code, such as a FastAPI route (step 09): while Gemini works, the server can do other work.
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

    # ⑥ What the engine holds and how it's set up: the API shows it at /api/stats (step 09).
    def stats(self) -> dict:
        return {"documents": len(self.documents), "chunks": len(self.chunks), "collection": COLLECTION,
                "chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap, "top_k": self.top_k,
                "embedding_model": EMBEDDING_MODEL, "chat_model": CHAT_MODEL}


if __name__ == "__main__":
    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS
    engine = RAGEngine()
    engine.build()
    print(f"Built: {engine.stats()['documents']} articles, {engine.stats()['chunks']} chunks\n")
    for question in questions:
        result = engine.query(question)
        print(f"Q: {question}\nA: {result['answer']}")
        for source in result["sources"]:
            print(f"   source: {source['title']} ({source['system']}, {source['category']})")
        print()
