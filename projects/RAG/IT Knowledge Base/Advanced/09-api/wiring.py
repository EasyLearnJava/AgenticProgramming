"""
IT Knowledge Base: Wiring the Parts
===================================

The one place where kb_settings.toml's settings become objects: pipeline.py, evaluation.py and main.py build their
parts here, so all of them get the same ones. It handles:
  1. make_embedder(): the embedding model (and its key, read first for Gemini), its cache and its limits
  2. make_store(): the Qdrant client (a server's key from QDRANT_API_KEY) and the store behind the alias
  3. make_reranker() and make_retriever(): the retriever with its parts: the client, the model, the question
     cache, the re-ranker, and the spellings it reads filters with
  4. make_answerer(): the chat model asked for a structured Answer (and bound to its JSON schema, to stream one),
     the versioned prompt, the budget and the judge
  5. make_engine(): the RAGEngine around the retriever and the answerer, with its cache, memory, condenser and
     breakers
  6. make_api(): the API around the engine, on the store pipeline.py filled, with its keys, rate limit and feedback

Making any of them reads no data and calls nothing, except reading the key and the prompt file.
"""
from pathlib import Path

from fastapi import FastAPI
from langchain_core.runnables import RunnableGenerator, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI

from answering import Answer, Answerer, Verdict, extractive_stand_in, load_prompt, streaming_stand_in
from api import create_app
from article import Spellings
from config import load_api_key, qdrant_api_key
from embedding import ChunkEmbedder, EmbeddingCache, make_embedding_model
from feedback import FeedbackStore
from manifest import Manifest
from rag_engine import AnswerCache, CircuitBreaker, ConversationMemory, RAGEngine, condense_by_rule, condense_with
from retriever import CrossEncoderReranker, KBRetriever, Reranker, WordOverlapReranker
from security import ApiKeys, RateLimiter
from settings import AnswerSettings, EmbeddingSettings, KBSettings, RetrievalSettings, VectorStoreSettings
from vector_store import KBVectorStore, make_client


def from_folder(path: Path, settings_file: Path) -> Path:
    """A path from the settings: as it is when absolute, else from the settings file's folder."""
    return path if path.is_absolute() else settings_file.resolve().parent / path


def cache_path(settings: EmbeddingSettings, settings_file: Path) -> Path:
    """The embedding cache's file, from the settings file's folder when it's relative."""
    return settings.cache_path if settings.cache_path.is_absolute() else \
        settings_file.resolve().parent / settings.cache_path


def make_embedder(settings: EmbeddingSettings, settings_file: Path) -> ChunkEmbedder:
    """The ChunkEmbedder kb_settings.toml describes: its model, its cache and its limits. Gemini needs the key: it's
    read here, before anything else is done."""
    api_key = load_api_key() if settings.provider == "google" else None
    model = make_embedding_model(provider=settings.provider, model=settings.model, dimensions=settings.dimensions,
                                 timeout_seconds=settings.timeout_seconds, api_key=api_key)
    return ChunkEmbedder(model, model_name=settings.model_name, dimensions=settings.dimensions,
                         cache=EmbeddingCache(cache_path(settings, settings_file), model=settings.model_name,
                                              dimensions=settings.dimensions),
                         batch_size=settings.batch_size, batch_tokens=settings.batch_tokens,
                         max_concurrency=settings.max_concurrency, max_attempts=settings.max_attempts,
                         timeout_seconds=settings.timeout_seconds, backoff_seconds=settings.backoff_seconds,
                         backoff_max_seconds=settings.backoff_max_seconds)


def make_store(settings: VectorStoreSettings, dimensions: int, settings_file: Path) -> KBVectorStore:
    """The KBVectorStore kb_settings.toml describes; a server's key comes from QDRANT_API_KEY."""
    key = qdrant_api_key() if settings.location.startswith(("http://", "https://")) else None
    client = make_client(settings.location, folder=settings_file.resolve().parent,
                         api_key=key.get_secret_value() if key else None)
    return KBVectorStore(client, dimensions=dimensions, alias=settings.alias, hnsw_m=settings.hnsw_m,
                         hnsw_ef_construct=settings.hnsw_ef_construct)


def make_query_cache(settings: EmbeddingSettings, settings_file: Path) -> EmbeddingCache:
    """The cache of question vectors: the embedding cache's file, under "<provider>/<model>#query" (a question is
    embedded for searching, not as a document, so its vector is kept apart)."""
    return EmbeddingCache(cache_path(settings, settings_file), model=f"{settings.model_name}#query",
                          dimensions=settings.dimensions)


def make_reranker(settings: RetrievalSettings) -> Reranker | None:
    """The re-ranker [retrieval] names: none, word overlap, or a cross-encoder (loaded in the retriever's build())."""
    if settings.reranker == "cross-encoder":
        return CrossEncoderReranker(settings.cross_encoder_model)
    return WordOverlapReranker() if settings.reranker == "word-overlap" else None


def make_retriever(settings: KBSettings, client, embeddings, *, reranker: Reranker | None,
                   query_cache: EmbeddingCache | None = None, mode: str | None = None) -> KBRetriever:
    """The KBRetriever [retrieval] describes, over the store's alias, with the parts passed in (mode overrides the
    setting, for comparing)."""
    retrieval = settings.retrieval
    return KBRetriever(client=client, embeddings=embeddings, model_name=settings.embeddings.model_name,
                       collection=settings.vectorstore.alias, query_cache=query_cache, mode=mode or retrieval.mode,
                       k=retrieval.k, candidates=retrieval.candidates, rrf_k=retrieval.rrf_k,
                       min_score=retrieval.min_score, max_per_article=retrieval.max_per_article,
                       mmr_lambda=retrieval.mmr_lambda, reranker=reranker, read_filters=retrieval.read_filters,
                       spellings={label: Spellings(table) for label, table in settings.spellings.items()})


def make_answerer(settings: AnswerSettings, settings_file: Path) -> Answerer:
    """The Answerer [answer] describes: Gemini asked for a structured Answer (and, with judge, a Verdict), and
    bound to Answer's JSON schema to stream one; or the extractive stand-in, streamed a word at a time. The prompt
    from its versioned file (from the settings file's folder)."""
    prompt_file = settings.prompt_file if settings.prompt_file.is_absolute() else \
        settings_file.resolve().parent / settings.prompt_file
    prompt = load_prompt(prompt_file)
    if settings.provider == "fake":
        return Answerer(RunnableLambda(extractive_stand_in), prompt=prompt,
                        max_context_tokens=settings.max_context_tokens, not_covered=settings.not_covered,
                        streamer=RunnableGenerator(streaming_stand_in))
    chat = ChatGoogleGenerativeAI(model=settings.model, api_key=load_api_key(), temperature=settings.temperature,
                                  max_output_tokens=settings.max_output_tokens, timeout=settings.timeout_seconds,
                                  max_retries=settings.max_attempts)
    # with_structured_output() parses the whole reply before it gives anything back, so the stream comes from the
    # model bound to the same JSON schema, read as it arrives
    streamer = chat.bind(response_mime_type="application/json", response_json_schema=Answer.model_json_schema())
    return Answerer(chat.with_structured_output(Answer, include_raw=True), prompt=prompt,
                    max_context_tokens=settings.max_context_tokens, not_covered=settings.not_covered,
                    judge=chat.with_structured_output(Verdict) if settings.judge else None, streamer=streamer)


def make_engine(settings: KBSettings, settings_file: Path, *, store: KBVectorStore, embedder: ChunkEmbedder,
                kb_version: str) -> RAGEngine:
    """The RAGEngine [engine] describes, around a retriever on the store and an answerer: the answer cache, the
    conversation memory, the condenser (Gemini with prompts/condense-v1.txt, or the stand-in's rule) and a breaker
    for the store and one for the model. kb_version: the manifest's version (Manifest.version())."""
    engine = settings.engine
    retriever = make_retriever(settings, store.client, embedder.model, reranker=make_reranker(settings.retrieval),
                               query_cache=make_query_cache(settings.embeddings, settings_file)).build()
    if settings.answer.provider == "fake":
        condenser = condense_by_rule
    else:
        chat = ChatGoogleGenerativeAI(model=settings.answer.model, api_key=load_api_key(), temperature=0.0,
                                      timeout=settings.answer.timeout_seconds, max_retries=settings.answer.max_attempts)
        condenser = condense_with(chat, load_prompt(from_folder(settings.answer.condense_prompt_file,
                                                                settings_file)).system)
    breaker = {"failures": engine.breaker_failures, "reset_seconds": engine.breaker_reset_seconds}
    return RAGEngine(
        retriever=retriever, answerer=make_answerer(settings.answer, settings_file), store=store,
        model_name=settings.answer.model_name, kb_version=kb_version,
        cache=AnswerCache(from_folder(engine.cache_path, settings_file), ttl_seconds=engine.cache_ttl_seconds,
                          threshold=engine.semantic_threshold) if engine.cache else None,
        memory=ConversationMemory(turns=engine.memory_turns) if engine.memory_turns else None, condenser=condenser,
        question_timeout_seconds=engine.question_timeout_seconds,
        store_breaker=CircuitBreaker("vector store", **breaker), model_breaker=CircuitBreaker("chat model", **breaker),
        prices_per_million=(engine.input_price_per_million, engine.output_price_per_million))


def make_api(settings: KBSettings, settings_file: Path, *, manifest_path: Path) -> FastAPI:
    """The API [api] describes, around the engine on the store pipeline.py filled: its callers' keys, their rate
    limit and the feedback store. The store's client is closed when the server stops."""
    store = make_store(settings.vectorstore, settings.embeddings.dimensions, settings_file)
    try:
        embedder = make_embedder(settings.embeddings, settings_file)
        engine = make_engine(settings, settings_file, store=store, embedder=embedder,
                             kb_version=Manifest(manifest_path).version())
        keys = ApiKeys.load(from_folder(settings.api.keys_file, settings_file))
    except Exception:
        store.client.close()
        raise
    return create_app(engine, keys=keys, limiter=RateLimiter(settings.api.requests_per_minute),
                      feedback=FeedbackStore(from_folder(settings.api.feedback_path, settings_file),
                                             keep_days=settings.api.keep_answered_days),
                      settings=settings.api, on_close=store.client.close)
