"""Stable upload identities, revision history, and reversible removal.

The cleaned filename INCLUDING its extension is the logical document identity.
Uploading a revision replaces the active bytes; previous bytes remain in history.
Removal is a registry flag, so normal app restore does not depend on file recovery.
"""

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from policylens.ingestion.loaders import SUPPORTED


class UploadRepository:
    def __init__(self, data: Path):
        self.folder = data / "uploads"
        self.history = data / "upload_history"
        self.registry = self.folder / "records.json"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)
        if not self.registry.exists():
            records = {}
            # Preserve old files; if old content hashes created revisions, newest wins.
            for path in sorted(self.folder.iterdir(), key=lambda p: p.stat().st_mtime):
                if path.suffix.lower() in SUPPORTED:
                    title = re.sub(r"-[a-f0-9]{16}$", "", path.stem) + path.suffix.lower()
                    source_id = self.identity(title)
                    records[source_id] = {"source_id": source_id, "file": path.name,
                        "title": title, "deleted": False, "revision": 1}
            self.save(records)

    @staticmethod
    def identity(filename: str) -> str:
        return "upload-" + hashlib.sha256(filename.casefold().encode()).hexdigest()[:24]

    @staticmethod
    def clean_name(filename: str) -> str:
        name = Path(filename.replace("\\", "/").rsplit("/", 1)[-1])
        stem = "".join(c for c in name.stem if c.isalnum() or c in "-_ ")[:70].strip() or "document"
        return stem + name.suffix.lower()

    def read(self) -> dict:
        return json.loads(self.registry.read_text(encoding="utf-8"))

    def save(self, records: dict):
        temporary = self.registry.with_suffix(".json.tmp")
        temporary.write_bytes(json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8"))
        temporary.replace(self.registry)

    def documents(self) -> list[dict]:
        docs = []
        for record in self.read().values():
            path = self.folder / Path(record["file"]).name
            if not record["deleted"] and path.is_file():
                docs.append({**record, "path": path, "category": "Uploaded", "kind": "Your document", "url": None,
                             "fetched_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
        return sorted(docs, key=lambda doc: doc["title"].casefold())

    def upload(self, filename: str, content: bytes) -> dict:
        title = self.clean_name(filename)
        source_id = self.identity(title)
        records = self.read()
        old = records.get(source_id)
        if old:
            previous = self.folder / old["file"]
            if previous.exists() and previous.read_bytes() == content:
                if old["deleted"]:
                    old["deleted"] = False
                    self.save(records)
                return {"file": old["file"], "source_id": source_id, "duplicate": True,
                        "message": "Identical document already stored; no bytes were rewritten."}
            if previous.exists():
                archive = self.history / source_id
                archive.mkdir(exist_ok=True)
                digest = hashlib.sha256(previous.read_bytes()).hexdigest()
                shutil.copy2(previous, archive / (digest + previous.suffix))
        path = self.folder / (source_id + Path(title).suffix)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        records[source_id] = {"source_id": source_id, "title": title, "file": path.name,
                              "revision": (old["revision"] + 1) if old else 1, "deleted": False}
        self.save(records)
        return {"file": path.name, "source_id": source_id, "duplicate": False, "replaced": bool(old),
                "message": "Revision replaced the active document; rebuild the index." if old else "Document added; rebuild the index."}

    def removed(self) -> list[dict]:
        return [dict(record) for record in self.read().values() if record["deleted"]]

    def set_removed(self, source_id: str, removed: bool):
        records = self.read()
        if source_id not in records:
            raise ValueError("Only uploaded documents can be removed or restored.")
        records[source_id]["deleted"] = removed
        self.save(records)
        return {"source_id": source_id, "message": "Document removed. Rebuild the index; restore is available." if removed else "Document restored. Rebuild the index."}

