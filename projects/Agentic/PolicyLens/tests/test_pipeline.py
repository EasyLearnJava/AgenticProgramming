"""Test the parts that can quietly break grounding or corrupt a usable index."""

import numpy as np
import pytest
import tiktoken
from langchain_core.documents import Document

from policylens.config import Settings
from policylens.generation import validate_draft
from policylens.ingestion.chunking import chunk_documents
from policylens.models import AnswerDraft, Claim, QuoteReference
from policylens.retrieval.embeddings import LocalHashEmbeddings


def test_chunks_preserve_page_and_heading_and_token_limit(tmp_path):
    docs = [Document(page_content="# Security\n\n## Passwords\n\n" + "Keep credentials private. " * 200,
                     metadata={"source_id": "security", "title": "Security", "location": "Page 2"})]
    settings = Settings(root=tmp_path, chunk_size=80, chunk_overlap=10)
    chunks = chunk_documents(docs, settings)
    assert len(chunks) > 2
    assert all("Page 2" in chunk.location and "Passwords" in chunk.location for chunk in chunks)
    encoder = tiktoken.get_encoding("cl100k_base")
    assert all(len(encoder.encode(chunk.text)) <= 80 for chunk in chunks)
    assert [c.id for c in chunks] == [c.id for c in chunk_documents(docs, settings)]


def test_hash_embeddings_are_stable_normalized_and_local():
    first = LocalHashEmbeddings().embed_query("Password SEC-101 password")
    second = LocalHashEmbeddings().embed_query("Password SEC-101 password")
    assert first == second
    assert len(first) == 768
    assert np.linalg.norm(first) == pytest.approx(1)


def test_cited_extraction_and_source_filter(service):
    answer = service.ask("What receipts are required for expenses?")
    assert answer.status == "evidence"
    assert answer.citations
    for citation in answer.citations:
        chunk = next(hit.chunk for hit in answer.retrieved if hit.chunk.id == citation.chunk_id)
        assert citation.quote in chunk.text
    answer = service.ask("What is security code SEC-101?", ["security"])
    assert answer.retrieved
    assert all(hit.chunk.source_id == "security" for hit in answer.retrieved)
    assert service.ask("What is security code SEC-101?", ["missing"]).status == "refused"


def test_ambiguous_and_unrelated_questions(service):
    assert service.ask("What is the policy?").status == "clarify"
    assert service.ask("What is Jupiter's orbital eccentricity?").status == "refused"


def test_model_citations_fail_closed(service):
    answer = service.ask("What receipts are required for expenses?")
    hit = answer.retrieved[0]
    quote = "Receipts are required for expenses over $50."
    draft = AnswerDraft(decision="answered", message="", claims=[
        Claim(text="Receipts are required over $50.", references=[QuoteReference(chunk_id=hit.chunk.id, quote=quote)])])
    text, citations = validate_draft(draft, answer.retrieved)
    assert "[1]" in text and citations[0].quote == quote
    draft.claims[0].references[0].quote = "No receipts are required for expenses."
    with pytest.raises(ValueError):
        validate_draft(draft, answer.retrieved)
    draft.claims[0].references[0] = QuoteReference(chunk_id="invented", quote=quote)
    with pytest.raises(ValueError):
        validate_draft(draft, answer.retrieved)


def test_stale_content_blocks_queries_until_rebuild(service):
    path = service.settings.data / "corpus" / "expenses.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nNew expense guidance.", encoding="utf-8")
    assert service.status()["needs_rebuild"]
    with pytest.raises(ValueError, match="Rebuild"):
        service.ask("What receipts are required?")
    service.rebuild()
    assert not service.status()["needs_rebuild"]


def test_failed_rebuild_preserves_previous_index(service):
    before = service.store.snapshot()[2]
    original = service.embeddings.embed_documents
    service.embeddings.embed_documents = lambda texts: (_ for _ in ()).throw(RuntimeError("provider unavailable"))
    with pytest.raises(RuntimeError):
        service.rebuild()
    assert service.store.snapshot()[2] == before
    service.embeddings.embed_documents = original
    assert service.ask("What receipts are required?").citations


def test_upload_is_contained_and_invalid_pdf_is_removed(service):
    result = service.upload("../../outside.txt", b"A readable policy about equipment and repairs.")
    assert (service.settings.data / "uploads" / result["file"]).is_file()
    assert ".." not in result["file"]
    before = set((service.settings.data / "uploads").iterdir())
    with pytest.raises(ValueError):
        service.upload("broken.pdf", b"This is not a PDF")
    assert set((service.settings.data / "uploads").iterdir()) == before

