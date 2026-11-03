"""Read-only knowledge browsers and a playground that explains the chat retriever's actual scores and selections."""

import json
from collections import defaultdict
from datetime import date
from functools import lru_cache
from time import perf_counter
from typing import Any, Literal
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nimbus.forms import read_form_fields
from nimbus.pages import render_page
from nimbus.parks import ParkKnowledge
from nimbus.retrieval_gate import RetrievalGate

router = APIRouter()
PARKS = {"zion": "Zion", "grand-canyon": "Grand Canyon", "yosemite": "Yosemite"}
PARK_CLASSES = {"zion": "zion", "grand-canyon": "canyon", "yosemite": "yosemite"}


class KnowledgeFilters(BaseModel):
    """Only bounded text and known filter fields are accepted from the address bar."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    q: str = Field(default="", max_length=120)
    park: Literal["", "zion", "grand-canyon", "yosemite"] = ""
    document: str = Field(default="", max_length=100, pattern=r"^[a-z0-9-]*$")
    chunk: str = Field(default="", max_length=120, pattern=r"^[a-z0-9_-]*$")


class RetrievalFilters(BaseModel):
    """A bounded question and explicit destination, with an optional valid date for the existing season filter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    q: str = Field(default="", max_length=1000)
    destination: str = Field(default="", max_length=101, pattern=r"^[a-z0-9_-]*$")
    visit_date: date | None = None

    @field_validator("visit_date", mode="before")
    @classmethod
    def empty_date(cls, value: object) -> object:
        """An empty HTML date field means no seasonal filtering."""
        return None if value == "" else value


def read_filters(request: Request) -> KnowledgeFilters:
    """Validate filters without reflecting validation internals or the visitor's search into errors."""
    try:
        return KnowledgeFilters.model_validate(dict(request.query_params))
    except ValidationError:
        raise HTTPException(400, "Invalid knowledge filters") from None


def read_catalog(request: Request) -> dict[str, Any]:
    """Reuse a public index snapshot per app instance, independent of the chat's feature flag or credentials."""
    if not hasattr(request.app.state, "knowledge_catalog"):
        service = request.app.state.park_knowledge
        if not isinstance(service, ParkKnowledge):
            service = ParkKnowledge(request.app.state.settings.parks_index_path)
        request.app.state.knowledge_catalog = service.inspection()
    catalog: dict[str, Any] = request.app.state.knowledge_catalog
    return catalog


def to_documents(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Group the actual index passages by document, preserving source provenance and embedding coverage."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in catalog["chunks"]:
        grouped[chunk["document_id"]].append(chunk)
    documents = []
    for identity, chunks in grouped.items():
        first = chunks[0]
        documents.append(
            {
                "id": identity,
                "title": first["title"],
                "park_id": first["park_id"],
                "park": PARKS.get(first["park_id"], first["park_id"]),
                "source_url": first["source_url"],
                "updated": max((item["source_updated_at"] or "" for item in chunks), default=""),
                "retrieved": max(item["fetched_at"] for item in chunks)[:10],
                "chunks": chunks,
                "count": len(chunks),
                "vectors": sum(bool(item["embedding"]) for item in chunks),
                "words": sum(len(item["text"].split()) for item in chunks),
            }
        )
    return sorted(documents, key=lambda item: (item["park"], item["title"], item["id"]))


def base_context(catalog: dict[str, Any], filters: KnowledgeFilters) -> dict[str, Any]:
    """Shared page statistics from stored records, rather than hard-coded corpus counts."""
    documents = to_documents(catalog)
    return {
        "catalog": catalog,
        "filters": filters,
        "parks": PARKS,
        "documents": documents,
        "source_count": len(documents),
        "chunk_count": len(catalog["chunks"]),
        "vector_count": sum(bool(item["embedding"]) for item in catalog["chunks"]),
    }


def chunk_url(identity: str, filters: KnowledgeFilters) -> str:
    """A link that selects a chunk while preserving the current public content filters."""
    params = {name: value for name, value in filters.model_dump().items() if value and name != "chunk"}
    params["chunk"] = identity
    return f"/knowledge/chunks?{urlencode(params)}#chunk-detail"


@lru_cache(maxsize=4)
def project_vectors(vectors: tuple[tuple[str, tuple[float, ...]], ...]) -> dict[str, Any]:
    """Project stored vectors to two principal components, with deterministic signs and bounded SVG coordinates."""
    if not vectors:
        return {"points": [], "variance": (0.0, 0.0)}
    import numpy as np

    # ① Center the complete index so filtering never moves unrelated points around the map.
    matrix = np.asarray([values for _, values in vectors], dtype=float)
    centered = matrix - matrix.mean(axis=0)
    if len(vectors) == 1:
        coordinates = np.zeros((1, 2))
        variance = [0.0, 0.0]
    else:
        _, singular, components = np.linalg.svd(centered, full_matrices=False)
        coordinates = np.zeros((len(vectors), 2))
        variance = [0.0, 0.0]
        total = float(np.square(singular).sum())
        for axis in range(min(2, len(singular))):
            direction = components[axis]
            sign = 1 if direction[np.abs(direction).argmax()] >= 0 else -1
            coordinates[:, axis] = centered @ direction * sign
            variance[axis] = round(float(singular[axis] ** 2) / total * 100, 1) if total else 0.0
    # ② Each point links to the exact chunk; no simulated query or arbitrary vector values are introduced.
    extent = np.maximum(np.abs(coordinates).max(axis=0), 0.001)
    points = [
        {
            "id": identity,
            "x": round(400 + float(coordinates[index, 0] / extent[0]) * 320, 2),
            "y": round(190 - float(coordinates[index, 1] / extent[1]) * 150, 2),
        }
        for index, (identity, _) in enumerate(vectors)
    ]
    return {"points": points, "variance": tuple(variance)}


@router.get("/knowledge/sources", response_class=HTMLResponse)
def source_documents(request: Request) -> HTMLResponse:
    """Browse official documents represented in the actual index, with text and park filters."""
    catalog, filters = read_catalog(request), read_filters(request)
    context = base_context(catalog, filters)
    query = filters.q.casefold()
    context["visible_documents"] = [
        item
        for item in context["documents"]
        if (not filters.park or item["park_id"] == filters.park)
        and (not query or query in f"{item['title']} {item['id']} {item['park']}".casefold())
    ]
    response = render_page(request, "knowledge_sources.html", context)
    response.headers["cache-control"] = "no-store"
    return response


@router.get("/knowledge/sources/{document_id}", response_class=HTMLResponse)
def source_document(request: Request, document_id: str) -> HTMLResponse:
    """Read the indexed passages from one source with a link to its full official document."""
    catalog = read_catalog(request)
    context = base_context(catalog, KnowledgeFilters())
    document = next((item for item in context["documents"] if item["id"] == document_id), None)
    if document is None:
        raise HTTPException(404, "Source document not found")
    context["document"] = document
    return render_page(request, "knowledge_document.html", context)


@router.get("/knowledge/chunks", response_class=HTMLResponse)
def stored_chunks(request: Request) -> HTMLResponse:
    """Inspect source passages, vector components and a PCA map without running a model or modifying the index."""
    catalog, filters = read_catalog(request), read_filters(request)
    context = base_context(catalog, filters)
    if filters.document and not any(item["id"] == filters.document for item in context["documents"]):
        raise HTTPException(404, "Source document not found")
    query = filters.q.casefold()
    chunks = [
        item
        for item in catalog["chunks"]
        if (not filters.park or item["park_id"] == filters.park)
        and (not filters.document or item["document_id"] == filters.document)
        and (not query or query in f"{item['text']} {item['title']} {item['section']} {item['id']}".casefold())
    ]
    selected = next((item for item in chunks if item["id"] == filters.chunk), None)
    if filters.chunk and selected is None:
        raise HTTPException(404, "Chunk not found in the current view")
    selected = selected or (chunks[0] if chunks else None)
    vectors = tuple((item["id"], tuple(item["embedding"])) for item in catalog["chunks"] if item["embedding"])
    projection = project_vectors(vectors)
    by_id = {item["id"]: item for item in chunks}
    context.update(
        chunks=chunks,
        selected=selected,
        vector_json=json.dumps(selected["embedding"], indent=2) if selected else "",
        variance=projection["variance"],
        points=[
            {
                **point,
                "chunk": by_id[point["id"]],
                "href": chunk_url(point["id"], filters),
                "color": PARK_CLASSES.get(by_id[point["id"]]["park_id"], "unknown"),
            }
            for point in projection["points"]
            if point["id"] in by_id
        ],
        chunk_url=lambda identity: chunk_url(identity, filters),
    )
    response = render_page(request, "knowledge_chunks.html", context)
    response.headers["cache-control"] = "no-store"
    return response


@router.get("/knowledge/retrieval", response_class=HTMLResponse)
async def retrieval_playground(request: Request) -> HTMLResponse:
    """Show an empty playground; questions are accepted only through the bounded POST endpoint."""
    if request.query_params:
        raise HTTPException(400, "Submit retrieval questions using the form")
    return await render_retrieval(request, RetrievalFilters())


async def read_retrieval_request(request: Request) -> RetrievalFilters:
    """Read one small URL-encoded body, rejecting foreign origins, duplicate fields and invalid values."""
    fields = await read_form_fields(request, max_bytes=16_384, max_fields=3)
    try:
        filters = RetrievalFilters.model_validate(fields)
        if not filters.q or not filters.destination:
            raise ValueError("A question and destination are required")
    except (ValidationError, ValueError):
        raise HTTPException(400, "Invalid retrieval inputs") from None
    return filters


@router.post("/api/knowledge/retrieval", response_class=HTMLResponse)
async def run_retrieval(request: Request) -> HTMLResponse:
    """Run a body-only question within bounded request and inference capacity, without saving it."""
    gate: RetrievalGate = request.app.state.retrieval_gate
    caller = request.client.host if request.client else "unknown"
    async with gate.reserve(caller):
        return await render_retrieval(request, await read_retrieval_request(request))


async def render_retrieval(request: Request, filters: RetrievalFilters) -> HTMLResponse:
    """Render the actual chat scores and selections without Gemini, weather calls, or index writes."""
    # ① Scope only to an explicit supported destination; a missing index has its existing unavailable state.
    catalog = read_catalog(request)
    if (
        catalog["available"]
        and filters.destination
        and not any(item["id"] == filters.destination for item in catalog["destinations"])
    ):
        raise HTTPException(400, "Choose a supported park or trail")
    if filters.q and not filters.destination:
        raise HTTPException(400, "Choose a park or trail before running retrieval")
    context = base_context(catalog, KnowledgeFilters())
    context.update(
        retrieval_filters=filters,
        result=None,
        elapsed_ms=0,
        retrieval_enabled=False,
        chunk_url=chunk_url,
        knowledge_filters=KnowledgeFilters(),
        menu_path="/knowledge/retrieval",
    )
    service = request.app.state.park_knowledge
    enabled = request.app.state.settings.parks_enabled and isinstance(service, ParkKnowledge)
    context["retrieval_enabled"] = enabled
    # ② Reuse the shared service and its existing embedding deadline, scope rules, fusion and context limits.
    if filters.q and enabled:
        started = perf_counter()
        context["result"] = await service.search(filters.destination, filters.q, filters.visit_date, explain=True)
        context["elapsed_ms"] = round((perf_counter() - started) * 1000)
        structlog.get_logger().info(
            "knowledge.call",
            tool="retrieval_playground",
            status=context["result"]["status"],
            ms=context["elapsed_ms"],
            indexVersion=service.index_version,
        )
    response = render_page(request, "knowledge_retrieval.html", context)
    response.headers["cache-control"] = "no-store"
    return response
