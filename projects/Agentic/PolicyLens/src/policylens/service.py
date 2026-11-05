"""Shared operations with short file/commit locks and pinned query snapshots."""

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from collections import Counter

from langsmith import tracing_context

from policylens.config import Settings
from policylens.ingestion.chunking import chunk_documents
from policylens.ingestion.loaders import SUPPORTED, load_bytes
from policylens.pipeline import build_pipeline
from policylens.retrieval.embeddings import make_embeddings
from policylens.retrieval.store import IndexStore, QuerySession
from policylens.uploads import UploadRepository


class PolicyService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._state_lock = threading.RLock()
        self._build_lock = threading.Lock()
        self.store = IndexStore(settings.db)
        self.embeddings = make_embeddings(settings)
        self.pipeline = build_pipeline(settings, self.embeddings)
        self.uploads = UploadRepository(settings.data)
        self._hash_cache = {}
        self._session_cache = None
        self._session_signature = None
        self._source_counts = {}

    def documents(self) -> list[dict]:
        manifest_path = self.settings.data / "corpus" / "sources.json"
        sources = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
        docs = []
        for source in sources:
            path = self.settings.data / "corpus" / Path(source["file"]).name
            if path.is_file():
                docs.append({**source, "path": path, "kind": "Starter corpus"})
        docs.extend(self.uploads.documents())
        return docs

    def corpus_hash(self, docs: list[dict], contents: dict[str, bytes] | None = None, *, force=False) -> str:
        digest = hashlib.sha256()
        for doc in sorted(docs, key=lambda item: item["source_id"]):
            digest.update(doc["source_id"].encode())
            digest.update(json.dumps({k: v for k, v in doc.items() if k != "path"}, sort_keys=True).encode())
            if contents is not None:
                content_hash = hashlib.sha256(contents[doc["source_id"]]).hexdigest()
            else:
                path = doc["path"]
                stat = path.stat()
                stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
                cached = self._hash_cache.get(path)
                # Stat-based reuse is bounded: periodically verify bytes even if timestamps match.
                if not force and cached and cached[0] == stamp and perf_counter() - cached[2] < 30:
                    content_hash = cached[1]
                else:
                    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                    self._hash_cache[path] = (stamp, content_hash, perf_counter())
            digest.update(content_hash.encode())
        return digest.hexdigest()

    def _index_session(self) -> QuerySession:
        stat = self.settings.db.stat()
        signature = (stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns)
        if self._session_cache is None or signature != self._session_signature:
            self._session_cache = self.store.session()
            self._session_signature = signature
            self._source_counts = Counter(chunk.source_id for chunk in self._session_cache.chunks)
        return self._session_cache

    def rebuild(self) -> dict:
        started = perf_counter()
        # Only competing builds serialize; status and existing queries remain usable.
        with self._build_lock:
            with self._state_lock:
                docs = self.documents()
                if not docs:
                    raise ValueError("Add a document before building the index.")
                contents = {doc["source_id"]: doc["path"].read_bytes() for doc in docs}
                fingerprint = self.corpus_hash(docs, contents)
            loaded = []
            for doc in docs:
                loaded.extend(load_bytes(contents[doc["source_id"]], doc["path"].suffix.lower(),
                                         {key: value for key, value in doc.items() if key != "path"}))
            chunks = chunk_documents(loaded, self.settings)
            # Tracing is disabled explicitly, even if inherited environment enables it.
            with tracing_context(enabled=False):
                vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks])
            public_docs = [{key: value for key, value in doc.items() if key != "path"} for doc in docs]
            with self._state_lock:
                if self.corpus_hash(self.documents(), force=True) != fingerprint:
                    raise ValueError("Documents changed during indexing. The previous index was kept; rebuild again.")
                self.store.replace(chunks, vectors, self.settings.index_identity, public_docs, fingerprint)
                self._session_cache = None
        return {"documents": len(docs), "chunks": len(chunks), "ms": round((perf_counter() - started) * 1000)}

    def status(self) -> dict:
        from policylens.evaluation import load_questions

        with self._state_lock:
            session = self._index_session()
            chunks, metadata = session.chunks, session.metadata
            documents = self.documents()
            changed = metadata.get("corpus_hash") != self.corpus_hash(documents)
            indexed_ids = {chunk.source_id for chunk in chunks}
            now = datetime.now(timezone.utc)
            stale = [doc["source_id"] for doc in documents
                     if (now - datetime.fromisoformat(doc["fetched_at"])).total_seconds() > self.settings.freshness_days * 86400]
            public = [{**{key: value for key, value in doc.items() if key != "path"},
                       "indexed": doc["source_id"] in indexed_ids,
                       "chunks": self._source_counts[doc["source_id"]]} for doc in documents]
        return {"app": "PolicyLens", "mode": self.settings.mode,
                "embedding": self.settings.embedding_identity,
                "chat_model": self.settings.chat_model if self.settings.mode == "openai" else None,
                "documents": public, "chunk_count": len(chunks),
                "built_at": metadata.get("built_at"), "needs_rebuild": changed or metadata.get("identity") != self.settings.index_identity,
                "stale_sources": stale, "top_k": self.settings.top_k,
                "chunk_size": self.settings.chunk_size, "chunk_overlap": self.settings.chunk_overlap,
                "latency_target_seconds": self.settings.latency_target,
                "freshness_days": self.settings.freshness_days,
                "evaluation_count": len(load_questions(self.settings.root))}

    def open_session(self) -> QuerySession:
        with self._state_lock:
            session = self._index_session()
            if (session.metadata.get("identity") != self.settings.index_identity
                    or session.metadata.get("corpus_hash") != self.corpus_hash(self.documents())):
                raise ValueError("Documents or settings changed. Rebuild the index before asking questions.")
            return session

    def ask(self, question: str, source_ids: list[str] | None = None, *, session: QuerySession | None = None):
        started = perf_counter()
        session = session or self.open_session()
        # Network calls hold no file/state lock; each request keeps one generation.
        with tracing_context(enabled=False):
            result = self.pipeline.invoke({"question": question, "source_ids": source_ids or [],
                                           "session": session})["result"]
        result.latency_ms = round((perf_counter() - started) * 1000, 1)
        return result

    def upload(self, filename: str, content: bytes) -> dict:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise ValueError("Upload .md, .txt or text-based .pdf files.")
        if not content or len(content) > 10 * 1024 * 1024:
            raise ValueError("Upload a nonempty file smaller than 10 MB.")
        try:
            load_bytes(content, suffix, {"source_id": "upload-validation", "title": filename})
        except Exception:
            raise ValueError("Could not read this document. Use UTF-8 text or a valid, unencrypted text PDF.") from None
        with self._state_lock:
            return self.uploads.upload(filename, content)

    def remove_document(self, source_id: str):
        with self._state_lock:
            return self.uploads.set_removed(source_id, True)

    def restore_document(self, source_id: str):
        with self._state_lock:
            return self.uploads.set_removed(source_id, False)

