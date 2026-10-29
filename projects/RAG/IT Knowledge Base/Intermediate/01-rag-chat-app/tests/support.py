"""
Ready-made objects for the tests, built the way the app builds them:

    articles(), chunks()       ->  the 10 articles, read with config.yaml's columns; their 28 chunks
    filled_store()             ->  a Qdrant store in memory holding the 28 chunks, with KeywordEmbeddings' vectors
    stand_in_engine(settings)  ->  the engine factory.py wires, with stand-ins for both models
    change(settings, ...)      ->  a copy of the settings with some values changed
    write_config(folder, ...)  ->  config.yaml copied into a folder, with some values changed
"""
from pathlib import Path

import yaml
from fakes import ANSWER, SIZE, KeywordEmbeddings, reply
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from qdrant_client import QdrantClient

from src.chunking.chunker import Chunker
from src.config.settings import CONFIG_FILE, Settings, load_settings
from src.ingestion.loader import KBLoader
from src.pipeline.factory import create_engine
from src.pipeline.rag_engine import RAGEngine
from src.vectordb.vector_store import QdrantStore


def articles() -> list[Document]:
    """The 10 articles of data/sample_it_kb.csv, with config.yaml's columns."""
    ingestion = load_settings().ingestion
    return KBLoader(ingestion.path, text_columns=ingestion.text_columns, metadata_columns=ingestion.metadata_columns,
                    required_columns=ingestion.required_columns).load()


def chunks() -> list[Document]:
    """The 28 chunks of the 10 articles, at 512 characters with 50 shared."""
    return Chunker(chunk_size=512, chunk_overlap=50).split(articles())


def filled_store(collection: str = "test_collection") -> QdrantStore:
    """A store in memory holding the 28 chunks, each with its KeywordEmbeddings vector."""
    stored = chunks()
    store = QdrantStore(QdrantClient(":memory:"), collection)
    store.recreate(SIZE)
    store.upsert(stored, KeywordEmbeddings().embed_documents([chunk.page_content for chunk in stored]))
    return store


def change(settings: Settings, **sections) -> Settings:
    """A copy of the settings with some values changed: change(settings, retrieval={"top_k": 2})."""
    return settings.model_copy(update={name: getattr(settings, name).model_copy(update=values)
                                       for name, values in sections.items()})


def stand_in_engine(settings: Settings, answers: list[str] | None = None, **models) -> RAGEngine:
    """The engine factory.py wires, with stand-ins for both models: it answers with `answers`, in turn."""
    chat = FakeMessagesListChatModel(responses=[reply(text) for text in answers or [ANSWER] * 20])
    return create_engine(settings, embedding_model=models.get("embedding_model", KeywordEmbeddings()),
                         chat_model=models.get("chat_model", chat))


def write_config(folder: Path, **changes) -> Path:
    """config.yaml, copied into folder with some sections changed (None: the section left out); its relative paths
    are made full first, so they still find the project's files."""
    raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    raw["ingestion"]["path"] = str(load_settings().ingestion.path)
    for section, values in changes.items():
        raw[section] = values if values is None else raw[section] | values
    path = folder / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path
