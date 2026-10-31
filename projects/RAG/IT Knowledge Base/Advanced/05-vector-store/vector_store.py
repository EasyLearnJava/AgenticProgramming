"""
IT Knowledge Base: The Vector Store
===================================

Stores each chunk as a point in Qdrant: safe to write again and again, quick to filter, and possible to rebuild while
the app keeps answering. It handles:
  1. KBVectorStore: a collection behind an alias (it_kb -> it_kb_v1), made on the first load, with a dense vector
     (the embedding) and a sparse one (the chunk's words) on each point, and payload indexes on the labels
  2. Idempotent writes: a point's ID comes from its chunk_id (a UUID 5), so writing a chunk again updates its point;
     a changed article's old chunks, and a removed article's points, are deleted
  3. Checks after each load: each article written holds exactly its chunks, and the collection's vectors are the
     right size and distance; points of an article that isn't in the knowledge base are reported, not deleted: only
     the manifest's removed articles, or a rebuild, delete an article's points
  4. Rebuilding without downtime: a new collection is filled and checked, then the alias moves to it in one step;
     the one before is kept, so rollback() moves it back
  5. sparse_vector(): a keyword vector made from a text's words, so exact terms (an error code) can be found later

    store = KBVectorStore(QdrantClient(path="data/qdrant"), dimensions=768)
    store.write(chunks, vectors, removed=["kb-..."], current=all_article_ids)   ->  StoreReport(added=39, ...)
"""
import logging
import re
import uuid
import warnings
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document
from qdrant_client import QdrantClient, models

logger = logging.getLogger(__name__)

# The defaults: kb_settings.toml's [vectorstore] can change each one
LOCATION = "data/qdrant"        # Qdrant on disk, in this process; or ":memory:", or a server's URL
ALIAS = "it_kb"                 # the name searches use; it points at it_kb_v1, it_kb_v2, ...
HNSW_M = 16                     # HNSW's links per point; a server uses them, Qdrant in a process ignores them
HNSW_EF_CONSTRUCT = 100

# The vectors on each point, by name: LangChain's QdrantVectorStore reads them with these names (Advanced 06)
DENSE = "dense"
SPARSE = "sparse"

# The labels searches filter on: each gets a payload index. A point's payload is LangChain's layout:
# {"page_content": the text, "metadata": {...}}, so a filter's key is "metadata.<label>"
INDEXED_LABELS = ("doc_id", "system", "category", "priority", "tags", "visibility", "team")

# A chunk_id always gives the same point ID: a UUID 5 in this project's own namespace
POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "it-knowledge-base/chunks")

# Points written, and IDs looked up, this many at a time
WRITE_BATCH = 256

# A word, for the sparse vector: letters, digits and underscores, in lower case
WORD = re.compile(r"\w+")


class StoreError(RuntimeError):
    """The store can't be written as asked, or a check failed; the message says why."""


def point_id(chunk_id: str) -> str:
    """The point ID of a chunk: the same chunk_id always gives the same one, so writing a chunk again updates it."""
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


def sparse_vector(text: str) -> models.SparseVector:
    """The text's words as a sparse vector: each word's index a CRC-32 of it (the same on every run and machine),
    its value how many times it's there. The collection weighs each word by how rare it is (IDF) when searching."""
    counts = Counter(zlib.crc32(word.encode("utf-8")) & 0x7FFFFFFF for word in WORD.findall(text.casefold()))
    indices = sorted(counts)
    return models.SparseVector(indices=indices, values=[float(counts[index]) for index in indices])


def make_client(location: str, *, folder: Path, api_key: str | None = None) -> QdrantClient:
    """A Qdrant client for a location: ":memory:", a server's http(s) URL (with its API key, if it has one), or a
    folder (from `folder` when it's relative) where Qdrant keeps its data, in this process."""
    if location == ":memory:":
        return QdrantClient(":memory:")
    if location.startswith(("http://", "https://")):
        # No version check when it's made: making a client makes no call (the first request finds a server that's down)
        return QdrantClient(url=location, api_key=api_key, check_compatibility=False)
    path = Path(location) if Path(location).is_absolute() else folder / location
    try:
        return QdrantClient(path=str(path))
    except RuntimeError as err:          # Qdrant in a process: one client per folder at a time
        raise StoreError(f"Qdrant's folder {path} is open in another process ({err}). Close that one, or use a "
                         "Qdrant server (location = its URL).") from None


# -------------------------------------------------
# StoreReport - What a Load Did
# -------------------------------------------------

@dataclass
class StoreReport:
    """What write() or rebuild() did, and what the checks found."""
    collection: str = ""             # the collection the alias points to after the load
    added: int = 0                   # points that weren't there
    updated: int = 0                 # points written again (the same chunk)
    deleted_stale: int = 0           # points of a changed article's chunks that are gone
    deleted_removed: int = 0         # points of articles removed from the knowledge base
    points: int = 0                  # points in the collection after the load
    rebuilt: bool = False            # rebuild(): a new collection, now behind the alias
    rebuilt_from: str = ""           # rebuild(): the collection the alias pointed to before (kept for rollback)
    problems: list[str] = field(default_factory=list)   # what the checks found; none: the load is consistent
    orphans: list[str] = field(default_factory=list)    # articles not in the knowledge base that still have points


# -------------------------------------------------
# KBVectorStore Class - Qdrant, Behind an Alias
# -------------------------------------------------

class KBVectorStore:
    """
    The knowledge base's points in Qdrant, behind an alias.

    Step 1: Configure: the constructor stores the client and the settings; nothing is read or made
    Step 2: write() adds and updates the chunks passed on, deletes what's gone, and checks the result;
            rebuild() fills a new collection and moves the alias to it only when it passes the checks
    """

    def __init__(self, client: QdrantClient, *, dimensions: int, alias: str = ALIAS, hnsw_m: int = HNSW_M,
                 hnsw_ef_construct: int = HNSW_EF_CONSTRUCT):
        """
        Args:
            client: a Qdrant client (make_client() makes the one kb_settings.toml names)
            dimensions: the size of every dense vector
            alias: the name searches use; the collections behind it are <alias>_v1, <alias>_v2, ...
            hnsw_m, hnsw_ef_construct: the HNSW index's settings, for a Qdrant server
        """
        self.client = client
        self.dimensions = dimensions
        self.alias = alias
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct

    # --- The collection behind the alias ---

    def current(self) -> str | None:
        """The collection the alias points to, or None before the first load."""
        for found in self.client.get_aliases().aliases:
            if found.alias_name == self.alias:
                return found.collection_name
        return None

    def ensure(self) -> str:
        """The collection behind the alias, made (as <alias>_v1) with the alias on the first load."""
        collection = self.current()
        if collection is None:
            collection = f"{self.alias}_v1"
            self._create(collection)
            self._point_alias_at(collection)
            logger.info("Made collection %s, behind the alias %s", collection, self.alias)
        return collection

    def _create(self, collection: str) -> None:
        """A collection with a dense vector and a sparse one per point, and a payload index on each label."""
        self.client.create_collection(
            collection,
            vectors_config={DENSE: models.VectorParams(size=self.dimensions, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
            hnsw_config=models.HnswConfigDiff(m=self.hnsw_m, ef_construct=self.hnsw_ef_construct))
        with warnings.catch_warnings(record=True) as warned:          # Qdrant in a process warns for each one
            warnings.simplefilter("always")
            for label in INDEXED_LABELS:
                self.client.create_payload_index(collection, field_name=f"metadata.{label}",
                                                 field_schema=models.PayloadSchemaType.KEYWORD)
        if warned:
            logger.info("Payload indexes asked for on %s: Qdrant in a process keeps none (a filter still works); "
                        "a Qdrant server keeps them", ", ".join(INDEXED_LABELS))

    def _point_alias_at(self, collection: str) -> None:
        """Move the alias to a collection: deleting and making it again are one operation, so a search never finds
        the alias missing."""
        operations: list = []
        if self.current() is not None:
            operations.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=self.alias)))
        operations.append(models.CreateAliasOperation(create_alias=models.CreateAlias(
            collection_name=collection, alias_name=self.alias)))
        self.client.update_collection_aliases(change_aliases_operations=operations)

    # --- Writing ---

    def write(self, chunks: list[Document], vectors: list[list[float]], *, removed: list[str] = (),
              current: set[str] | None = None) -> StoreReport:
        """
        Add or update the chunks' points, delete the old chunks of each article written and every point of the
        removed articles, then check the collection.

        Args:
            chunks, vectors: the chunks of the articles passed on, and their vectors, in the same order
            removed: the IDs of articles no longer in the knowledge base (the manifest's removed list)
            current: the IDs of every article the knowledge base holds now; points of any other article are reported
                     as orphans, not deleted

        Raises:
            StoreError: a vector isn't the collection's size (nothing is written), or a check failed
        """
        collection = self.ensure()
        size = self.client.get_collection(collection).config.params.vectors[DENSE].size
        if size != self.dimensions:            # another model, or another size: its vectors can't mix with these
            raise StoreError(f"{collection} holds vectors of {size} numbers, but the embedding model makes "
                             f"{self.dimensions}: nothing written. Run with --rebuild to make a new collection.")
        report = StoreReport(collection=collection)
        self._write_to(collection, chunks, vectors, removed, report)
        report.problems = self.check(collection, chunks)
        report.orphans = self.orphans(collection, current) if current is not None else []
        report.points = self.client.count(collection, exact=True).count
        if report.problems:
            raise StoreError(f"The checks on {collection} failed: {'; '.join(report.problems)}")
        return report

    def rebuild(self, chunks: list[Document], vectors: list[list[float]]) -> StoreReport:
        """
        Fill a new collection with every chunk, check it, then move the alias to it in one step; the collection the
        alias pointed to stays, for rollback(), and any older one is deleted. A failed check deletes the new
        collection and leaves the alias, and the live collection, as they were.

        Raises:
            StoreError: a vector isn't the right size, or a check on the new collection failed
        """
        before = self.current()
        version = int(before.rsplit("_v", 1)[1]) + 1 if before and "_v" in before else 1
        collection = f"{self.alias}_v{version}"
        if self.client.collection_exists(collection):
            self.client.delete_collection(collection)
        self._create(collection)
        report = StoreReport(collection=collection, rebuilt=True, rebuilt_from=before or "")
        try:
            self._write_to(collection, chunks, vectors, [], report)
            report.problems = self.check(collection, chunks)
            report.points = self.client.count(collection, exact=True).count
            if report.problems:
                raise StoreError(f"The checks on the new collection {collection} failed, so the alias {self.alias} "
                                 f"still points at {before}: {'; '.join(report.problems)}")
        except Exception:
            self.client.delete_collection(collection)
            raise
        self._point_alias_at(collection)
        for old in self._versions():
            if old not in (collection, before):
                self.client.delete_collection(old)
        logger.info("Rebuilt: the alias %s now points at %s (%s kept for rollback)", self.alias, collection, before)
        return report

    def rollback(self) -> str:
        """Move the alias back to the collection before the current one, and return its name.

        Raises:
            StoreError: there's no earlier collection to go back to
        """
        current = self.current()
        earlier = [name for name in self._versions() if name != current and self._version(name) <
                   self._version(current or "")]
        if not earlier:
            raise StoreError(f"There's no collection before {current} to go back to")
        self._point_alias_at(earlier[-1])
        return earlier[-1]

    def _write_to(self, collection: str, chunks: list[Document], vectors: list[list[float]], removed,
                  report: StoreReport) -> None:
        """Add or update the points, then delete what's gone; the counts go into the report."""
        if len(vectors) != len(chunks):
            raise StoreError(f"{len(chunks)} chunks but {len(vectors)} vectors: nothing written")
        wrong = [len(vector) for vector in vectors if len(vector) != self.dimensions]
        if wrong:
            raise StoreError(f"A vector of {wrong[0]} numbers, not {self.dimensions}: nothing written to "
                             f"{collection}")
        points = [models.PointStruct(id=point_id(chunk.metadata["chunk_id"]),
                                     vector={DENSE: vector, SPARSE: sparse_vector(chunk.page_content)},
                                     payload={"page_content": chunk.page_content, "metadata": chunk.metadata})
                  for chunk, vector in zip(chunks, vectors, strict=True)]
        ids = [point.id for point in points]
        there = {str(found.id) for start in range(0, len(ids), WRITE_BATCH)
                 for found in self.client.retrieve(collection, ids[start:start + WRITE_BATCH], with_payload=False,
                                                   with_vectors=False)}
        for start in range(0, len(points), WRITE_BATCH):
            self.client.upsert(collection, points=points[start:start + WRITE_BATCH], wait=True)
        report.updated = sum(point_id_ in there for point_id_ in ids)
        report.added = len(ids) - report.updated

        # A changed article's chunks that aren't among its new ones: written first, then the old ones deleted, so
        # the article is never missing from the store
        by_article: dict[str, list[str]] = defaultdict(list)
        for chunk, id_ in zip(chunks, ids, strict=True):
            by_article[chunk.metadata["doc_id"]].append(id_)
        for doc_id, kept in by_article.items():
            stale = models.Filter(must=[_is_article(doc_id)], must_not=[models.HasIdCondition(has_id=kept)])
            report.deleted_stale += self._delete(collection, stale)
        if removed:
            report.deleted_removed = self._delete(collection, models.Filter(must=[models.FieldCondition(
                key="metadata.doc_id", match=models.MatchAny(any=list(removed)))]))

    def _delete(self, collection: str, selector: models.Filter) -> int:
        """Delete the points a filter selects; how many there were."""
        count = self.client.count(collection, count_filter=selector, exact=True).count
        if count:
            self.client.delete(collection, points_selector=models.FilterSelector(filter=selector), wait=True)
        return count

    # --- Checking ---

    def check(self, collection: str, chunks: list[Document]) -> list[str]:
        """What's wrong with the collection, if anything: its vectors' size and distance, and each article written
        holding exactly its chunks' points."""
        problems = []
        dense = self.client.get_collection(collection).config.params.vectors[DENSE]
        if dense.size != self.dimensions or dense.distance != models.Distance.COSINE:
            problems.append(f"its vectors are {dense.size} numbers by {dense.distance.value}, not "
                            f"{self.dimensions} by Cosine")
        expected: dict[str, set[str]] = defaultdict(set)
        for chunk in chunks:
            expected[chunk.metadata["doc_id"]].add(point_id(chunk.metadata["chunk_id"]))
        stored = self._points_by_article(collection)
        for doc_id, ids in expected.items():
            if stored.get(doc_id, set()) != ids:
                problems.append(f"article {doc_id} holds {len(stored.get(doc_id, set()))} points, not its "
                                f"{len(ids)} chunks")
        return problems

    def orphans(self, collection: str, current: set[str]) -> list[str]:
        """The IDs of articles that still have points but aren't in the knowledge base now: left by a run that
        failed, or removed while the manifest was being ignored (--full). A rebuild clears them."""
        return sorted(set(self._points_by_article(collection)) - current)

    def _points_by_article(self, collection: str) -> dict[str, set[str]]:
        """Every point's ID, by its article's ID."""
        found: dict[str, set[str]] = defaultdict(set)
        offset = None
        while True:
            points, offset = self.client.scroll(collection, limit=WRITE_BATCH, offset=offset,
                                                with_payload=["metadata.doc_id"], with_vectors=False)
            for point in points:
                found[point.payload["metadata"]["doc_id"]].add(str(point.id))
            if offset is None:
                return found

    def _versions(self) -> list[str]:
        """The alias's collections (<alias>_v1, _v2, ...), oldest first."""
        names = [found.name for found in self.client.get_collections().collections
                 if re.fullmatch(rf"{re.escape(self.alias)}_v\d+", found.name)]
        return sorted(names, key=self._version)

    def _version(self, name: str) -> int:
        return int(name.rsplit("_v", 1)[1]) if "_v" in name else 0


def _is_article(doc_id: str) -> models.FieldCondition:
    return models.FieldCondition(key="metadata.doc_id", match=models.MatchValue(value=doc_id))
