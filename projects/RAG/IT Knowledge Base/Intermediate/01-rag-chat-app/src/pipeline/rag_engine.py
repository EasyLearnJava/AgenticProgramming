"""
IT Knowledge Base: The RAG Engine
=================================

The whole pipeline as one object, wired from the parts it's handed: it never picks a provider itself (factory.py
does). build() is the ingestion half, run once per start; query() and aquery() are the query half, run for each
question. It handles:
  1. Build: load the articles, split them into chunks, take the chunks' vectors from the vector file when it holds
     exactly theirs (else embed them), and store them in a new collection
  2. Index: load, split and embed, then save the vectors in the vector file, for each later build to load
  3. Answer: find the closest chunks, fill in the prompt with them and the question, and ask the model
  4. Sources: up to max_sources different articles among the chunks found, each with a snippet and its score
  5. A span for the build, the indexing and each question, around the spans of the parts inside it; the question,
     the prompt and the answer at DEBUG, so a trace shows what the model was given and what it said
  6. Readiness: built, and the store still holds every chunk

    question -> retriever (embed, search) -> chunks ──┐
    question ─────────────────────────────────────────┴─> prompt -> LLM client -> answer + sources

Usage:
    engine = create_engine(settings, api_key)     # factory.py: the parts config.yaml names
    engine.build()                                ->  read, chunk, embed (one call per 100 chunks; none when the
                                                      vector file holds the chunks' vectors) and store
    engine.index()                                ->  28: read, chunk, embed, save the vectors (python main.py index)
    engine.query(question)                        ->  QueryResult: the answer and its sources (two calls)
    await engine.aquery(question)                 ->  the same, for async code such as the API's routes
"""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from src.chunking.chunker import Chunker
from src.embeddings.embedder import Embedder
from src.embeddings.vector_file import VectorFile
from src.exceptions import ConfigError, NotReadyError
from src.llm.llm_client import LLMClient, LLMResponse
from src.observability.tracing import NO_TRACE, current_trace_id, span
from src.prompts.prompt_templates import ANSWER_PROMPT, PROMPT_VERSION, format_context
from src.retrieval.retriever import KBRetriever
from src.utils.helpers import truncate
from src.vectordb.vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    """One article an answer's chunks came from. They're what the model was given, not a checked list of what its
    answer used: an answer can use fewer, or none."""
    title: str
    system: str
    category: str
    snippet: str
    score: float
    doc_id: str
    chunk_id: str


@dataclass(frozen=True)
class QueryResult:
    answer: str
    sources: list[Source]


class RAGEngine:
    """
    The RAG pipeline as one object.

    Step 1: Configure: the constructor stores the parts; nothing is read and no call is made
    Step 2: Build: build() loads and splits the articles, loads or embeds the chunks' vectors, and stores them; or
            index() embeds them and saves their vectors, for each later build to load
    Step 3: Answer: query() or aquery() answers one question with its sources
    """

    def __init__(self, *, loader: BaseLoader, chunker: Chunker, embedder: Embedder, store: BaseVectorStore,
                 retriever: KBRetriever, llm: LLMClient, max_sources: int, snippet_length: int,
                 vector_file: VectorFile | None = None):
        self.loader, self.chunker, self.embedder, self.store = loader, chunker, embedder, store
        self.retriever, self.llm = retriever, llm
        self.max_sources, self.snippet_length = max_sources, snippet_length
        self.vector_file = vector_file              # None: no saved vectors, so every build embeds the chunks
        self.documents: list[Document] = []
        self.chunks: list[Document] = []
        self.built_at: datetime | None = None
        self.build_trace_id: str | None = None      # the build's trace: the page shows how the knowledge base was built

    def build(self) -> None:
        """Load and split the articles; take the chunks' vectors from the vector file when it holds exactly theirs, or
        else embed them; store them in a new collection. Raises AppError."""
        with span("pipeline.build") as fields:
            documents, chunks = self._load_and_split()
            texts = [chunk.page_content for chunk in chunks]
            saved = self.vector_file.load(texts) if self.vector_file else None
            vectors = saved if saved is not None else self.embedder.embed_documents(texts)
            # The vectors are in hand before the old collection goes: a failed call leaves the old chunks searchable
            self.store.recreate(self.embedder.dimensions)
            self.store.upsert(chunks, vectors)
            self.documents, self.chunks = documents, chunks
            self.built_at = datetime.now(UTC)
            self.build_trace_id = None if current_trace_id() == NO_TRACE else current_trace_id()
            fields.update(documents=len(documents), chunks=len(chunks),
                          vectors_from="file" if saved is not None else "model")

    def index(self) -> int:
        """Load and split the articles, embed the chunks, and save their vectors in the vector file, for each later
        build to load (python main.py index). Returns how many were saved. Raises AppError."""
        if self.vector_file is None:
            raise ConfigError("embeddings.vector_file in config.yaml is null: there's no file to save the vectors in")
        with span("pipeline.index") as fields:
            documents, chunks = self._load_and_split()
            texts = [chunk.page_content for chunk in chunks]
            self.vector_file.save(texts, self.embedder.embed_documents(texts))
            fields.update(documents=len(documents), chunks=len(chunks))
            return len(chunks)

    def query(self, question: str) -> QueryResult:
        """Answer one question with its sources. Raises NotReadyError before build(), or the parts' AppErrors."""
        self._require_built()
        with span("pipeline.query", question_chars=len(question)) as fields:
            logger.debug("Question", extra={"question": question})
            found = self.retriever.invoke(question)
            response = self.llm.generate(self._messages(found, question))
            return self._result(found, response, fields)

    async def aquery(self, question: str) -> QueryResult:
        """The same, for async code: the server can do other work while the providers answer."""
        self._require_built()
        with span("pipeline.query", question_chars=len(question)) as fields:
            logger.debug("Question", extra={"question": question})
            found = await self.retriever.ainvoke(question)
            response = await self.llm.agenerate(self._messages(found, question))
            return self._result(found, response, fields)

    def check_ready(self) -> int:
        """How many chunks the store holds, if the engine is built and none are missing; else NotReadyError."""
        self._require_built()
        stored = self.store.count()
        if stored != len(self.chunks):
            raise NotReadyError(f"The vector store holds {stored} chunks, but the build stored {len(self.chunks)}")
        return stored

    def stats(self) -> dict:
        """What the engine holds and how it's set up, read from its parts: what runs, not the defaults."""
        return {"documents": len(self.documents), "chunks": len(self.chunks), "collection": self.store.collection,
                "chunk_size": self.chunker.chunk_size, "chunk_overlap": self.chunker.chunk_overlap,
                "top_k": self.retriever.k, "embedding_model": self.embedder.model_name,
                "chat_model": self.llm.model_name, "prompt_version": PROMPT_VERSION,
                "built_at": self.built_at.isoformat(timespec="seconds") if self.built_at else None,
                "build_trace_id": self.build_trace_id}

    def _require_built(self) -> None:
        if self.built_at is None:
            raise NotReadyError("The engine isn't built yet: build() must run first")

    def _load_and_split(self) -> tuple[list[Document], list[Document]]:
        """The articles and their chunks: one way for build() and index(), so saved vectors are for the same chunks."""
        documents = self.loader.load()
        return documents, self.chunker.split(documents)

    @staticmethod
    def _messages(found: list[Document], question: str) -> list:
        """What the model gets: the prompt, filled in with the chunks found and the question. A stage of its own, so
        it has its place in the trace's order; the messages are logged at DEBUG, so a trace shows exactly what the
        model was given."""
        with span("prompts.build", prompt_version=PROMPT_VERSION, chunks=len(found)) as fields:
            messages = ANSWER_PROMPT.format_messages(context=format_context(found), question=question)
            fields["prompt_chars"] = sum(len(message.content) for message in messages)
            logger.debug("Prompt", extra={"prompt_version": PROMPT_VERSION, "chunks": len(found),
                                          "messages": [{"role": message.type, "content": message.content}
                                                       for message in messages]})
            return messages

    def _result(self, found: list[Document], response: LLMResponse, fields: dict) -> QueryResult:
        """The answer, and the first max_sources different articles among the chunks found."""
        sources: list[Source] = []
        for chunk in found:
            metadata = chunk.metadata
            if any(source.doc_id == metadata["doc_id"] for source in sources):    # two chunks, one article
                continue
            sources.append(Source(title=metadata["title"], system=metadata.get("system", ""),
                                  category=metadata.get("category", ""),
                                  snippet=truncate(chunk.page_content, self.snippet_length),
                                  score=round(metadata["score"], 4), doc_id=metadata["doc_id"],
                                  chunk_id=metadata["chunk_id"]))
            if len(sources) == self.max_sources:
                break
        fields.update(sources=len(sources), answer_chars=len(response.text), prompt_version=PROMPT_VERSION)
        logger.debug("Answer", extra={"answer": response.text})
        return QueryResult(answer=response.text, sources=sources)
