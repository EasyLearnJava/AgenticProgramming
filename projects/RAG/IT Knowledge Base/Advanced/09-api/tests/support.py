"""
Helpers the tests share: the sample's chunks, a settings file whose embedding model is the stand-in, and a retriever
over Qdrant in memory holding the sample's chunks, embedded by the keyword stand-in (fakes.KeywordEmbeddings).
"""
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from fakes import KeywordEmbeddings
from langchain_core.documents import Document
from qdrant_client import QdrantClient

from article import Spellings
from chunking import KBTextSplitter
from knowledge_base_loader import KB_FILE, SETTINGS_FILE, KBLoader
from retriever import KBRetriever
from settings import load_settings
from vector_store import KBVectorStore

SETTINGS = load_settings(SETTINGS_FILE)
SPELLINGS = {label: Spellings(table) for label, table in SETTINGS.spellings.items()}


def sample_chunks() -> list[Document]:
    """The sample's 39 chunks, made fresh (later steps add to their metadata)."""
    docs = KBLoader(KB_FILE, settings=SETTINGS, clock=lambda: datetime(2026, 10, 30, tzinfo=UTC)).load()
    return KBTextSplitter().split_documents(docs)


def fake_settings(folder: Path) -> Path:
    """A copy of kb_settings.toml in `folder`, with the stand-in models (embedding and chat), and the prompt files
    beside it; its cache and its Qdrant go in folder/data/."""
    (folder / "prompts").mkdir(parents=True, exist_ok=True)
    for prompt in (SETTINGS_FILE.parent / "prompts").glob("*.txt"):
        (folder / "prompts" / prompt.name).write_text(prompt.read_text(encoding="utf-8"), encoding="utf-8")
    path = folder / "kb_settings.toml"
    path.write_text(SETTINGS_FILE.read_text(encoding="utf-8").replace('provider = "google"', 'provider = "fake"'),
                    encoding="utf-8")
    return path


@cache
def keyword_store() -> KBVectorStore:
    """Qdrant in memory with the sample's chunks, embedded by the keyword stand-in; made once, only searched."""
    model = KeywordEmbeddings()
    store = KBVectorStore(QdrantClient(":memory:"), dimensions=model.dimensions)
    chunks = sample_chunks()
    store.write(chunks, [model.vector(chunk.page_content) for chunk in chunks])
    return store


def keyword_retriever(**options) -> KBRetriever:
    """A retriever over keyword_store(), with the project's spellings; options set the rest."""
    options.setdefault("embeddings", KeywordEmbeddings())
    return KBRetriever(client=keyword_store().client, model_name="fake/keywords", spellings=SPELLINGS, **options)
