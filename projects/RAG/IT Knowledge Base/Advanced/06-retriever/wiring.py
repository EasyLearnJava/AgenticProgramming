"""
IT Knowledge Base: Wiring the Parts
===================================

The one place where kb_settings.toml's settings become objects: pipeline.py and evaluation.py build their parts here,
so both get the same ones. It handles:
  1. make_embedder(): the embedding model (and its key, read first for Gemini), its cache and its limits
  2. make_store(): the Qdrant client (a server's key from QDRANT_API_KEY) and the store behind the alias
  3. make_reranker() and make_retriever(): the retriever with its parts: the client, the model, the question
     cache, the re-ranker, and the spellings it reads filters with

Making any of them reads no data and calls nothing, except reading the key.
"""
from pathlib import Path

from article import Spellings
from config import load_api_key, qdrant_api_key
from embedding import ChunkEmbedder, EmbeddingCache, make_embedding_model
from retriever import CrossEncoderReranker, KBRetriever, Reranker, WordOverlapReranker
from settings import EmbeddingSettings, KBSettings, RetrievalSettings, VectorStoreSettings
from vector_store import KBVectorStore, make_client


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
