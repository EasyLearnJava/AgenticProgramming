"""Round-two failures: language variation, output meaning, lifecycle and real boundaries."""

import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from policylens.api import create_app
from policylens.generation import generate_openai, validate_draft
from policylens.grounding import EvidenceProfile, assess_evidence, is_ambiguous, request_issue
from policylens.ingestion.chunking import chunk_documents
from policylens.models import AnswerDraft, Chunk, Claim, QuoteReference, SearchHit
from policylens.retrieval.embeddings import LocalHashEmbeddings
from policylens.text import clean_text, normalize, tokens
from policylens.uploads import UploadRepository
from policylens.evaluation import score_case


def test_real_stems_contractions_and_hyphen_features():
    assert tokens("approves") == tokens("approval") == tokens("approving")
    assert tokens("shouldn't share") == tokens("should not share")
    assert set(tokens("non-US")) >= set(tokens("non US"))
    assert "café" in tokens("café")
    assert np.linalg.norm(LocalHashEmbeddings().embed_query("有給休暇")) > 0


@pytest.mark.parametrize("question", ["What is the rule?", "Tell me about the process", "How does it work?", "What should I do?"])
def test_one_topic_definition_controls_ambiguity(service, question):
    assert is_ambiguous(question)
    assert service.ask(question).status == "clarify"


def test_navigation_is_distinct_from_a_personal_record_lookup():
    assert request_issue("Where can I see my public holiday balance?") is None
    assert request_issue("What is my public holiday balance?")
    assert request_issue("Which policy says to ignore previous instructions?") is None


def test_plain_text_and_quotes_keep_content(service):
    text = "Use https://example.com/?id=3&region=us and keep &not-an-entity literally."
    assert clean_text(text) == text
    assert normalize("Receipts — required") == normalize("Receipts - required")
    uploaded = service.upload("links.txt", text.encode())
    assert (service.settings.data / "uploads" / uploaded["file"]).read_text() == text


def test_unicode_upload_can_be_retrieved(service):
    uploaded = service.upload("休暇.txt", "有給休暇は年間20日です。申請には承認が必要です。".encode())
    service.rebuild()
    answer = service.ask("有給休暇", [uploaded["source_id"]])
    assert answer.status == "evidence" and answer.citations


def test_chunks_are_original_spans_and_have_bodies(service):
    text = "# Policy\n\n## Empty heading\n\n## Rules\n\nKeep  two spaces and a\ttab in this source paragraph.\n"
    doc = Document(page_content=text, metadata={"source_id":"test", "title":"Policy"})
    chunks = chunk_documents([doc], service.settings)
    assert chunks and all(chunk.text in text for chunk in chunks)
    assert all("source paragraph" in chunk.text for chunk in chunks)


def test_quotes_need_body_evidence_and_cannot_reverse_the_same_claim(service):
    answer = service.ask("What receipts are required for expenses?")
    chunk = answer.retrieved[0].chunk
    draft = AnswerDraft(decision="answered", message="", claims=[Claim(
        text="Receipts are never required for expenses over $50.", references=[QuoteReference(
            chunk_id=chunk.id, quote="Receipts are required for expenses over $50.")])])
    with pytest.raises(ValueError, match="contradicts"):
        validate_draft(draft, answer.retrieved)
    heading = chunk.model_copy(update={"text":"## Receipt approval requirements\n\nBody text gives another rule."})
    hits = [answer.retrieved[0].model_copy(update={"chunk":heading})]
    draft.claims[0].references[0].quote = "Receipt approval requirements"
    with pytest.raises(ValueError):
        validate_draft(draft, hits)


def test_semantic_verifier_rejects_valid_quote_with_wrong_amount(service, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key")
    hits = service.ask("What receipts are required for expenses?").retrieved
    draft = {"decision":"answered", "message":"", "claims":[{"text":"Receipts are required over $500.",
        "references":[{"chunk_id":hits[0].chunk.id,"quote":"Receipts are required for expenses over $50."}]}]}
    seen = []

    def respond(request):
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        seen.append(name)
        result = {"complete_answer":True,"claims":[{"claim_index":0,"verdict":"unsupported"}]} if name == "AnswerReview" else draft
        return httpx.Response(200,json={"id":"test","object":"chat.completion","created":1,"model":"gpt-4.1-mini",
            "choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":json.dumps(result)}}],
            "usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}})

    factory = lambda: httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr("policylens.generation.create_http_client", factory)
    result = generate_openai("What receipt threshold applies?",hits,replace(service.settings,mode="openai"))
    assert result[0] == "refused" and not result[2]
    assert seen == ["AnswerDraft","AnswerReview"]


def test_neural_mode_does_not_require_literal_paraphrase_terms():
    chunk = Chunk(id="x",source_id="x",title="Leave",text="A team lead may grant annual leave.",location="Leave")
    hit = SearchHit(chunk=chunk,score=.5,keyword_score=0,vector_score=.65,coverage=0)
    profile = EvidenceProfile([chunk])
    assert assess_evidence("Who authorizes vacation?",[hit],profile,mode="openai")[0]
    assert not assess_evidence("Who authorizes vacation?",[hit],profile,mode="extractive")[0]


def test_revisions_replace_active_document_and_can_be_removed_and_restored(service):
    first = service.upload("remote.md", b"Remote work is permitted for every eligible test employee.")
    revised = service.upload("remote.md", b"Remote work is prohibited for this test policy.")
    assert first["source_id"] == revised["source_id"] and revised["replaced"]
    active = [doc for doc in service.documents() if doc["category"] == "Uploaded"]
    assert len(active) == 1
    assert len(list((service.settings.data / "upload_history" / first["source_id"]).glob("*.md"))) == 1
    service.rebuild()
    assert "prohibited" in service.ask("Remote work",[first["source_id"]]).text
    with TestClient(create_app(service),base_url="http://localhost") as client:
        assert client.delete("/api/documents/" + first["source_id"]).status_code == 200
        assert not any(doc["source_id"] == first["source_id"] for doc in service.documents())
        assert client.get("/api/documents/removed").json()[0]["source_id"] == first["source_id"]
        assert client.post("/api/documents/" + first["source_id"] + "/restore").status_code == 200
        assert any(doc["source_id"] == first["source_id"] for doc in service.documents())


def test_same_bytes_different_extensions_have_distinct_ids(service):
    data = b"An uploaded policy with the same content in two supported formats."
    md, txt = service.upload("same.md",data), service.upload("same.txt",data)
    assert md["source_id"] != txt["source_id"]
    service.rebuild()
    assert len({c.source_id for c in service.open_session().chunks if c.category == "Uploaded"}) == 2


def test_legacy_revision_migration_preserves_files_and_selects_latest(tmp_path):
    import os
    folder = tmp_path / "uploads"
    folder.mkdir()
    old, latest = folder / "remote-aaaaaaaaaaaaaaaa.txt", folder / "remote-bbbbbbbbbbbbbbbb.txt"
    old.write_bytes(b"Old version."); latest.write_bytes(b"Latest version.")
    os.utime(old,(1,1)); os.utime(latest,(2,2))
    repository = UploadRepository(tmp_path)
    assert len(repository.documents()) == 1
    assert repository.documents()[0]["path"].read_bytes() == b"Latest version."
    assert old.exists() and latest.exists()


def test_warm_status_and_queries_reuse_snapshot_and_file_hashes(service, monkeypatch):
    service.status()
    reads = []
    original = Path.read_bytes

    def read(path):
        if "corpus" in path.parts:
            reads.append(path)
        return original(path)

    monkeypatch.setattr(Path,"read_bytes",read)
    monkeypatch.setattr(service.store,"session",lambda: pytest.fail("Warm request reloaded vectors"))
    service.status(); service.ask("What receipts are required?"); service.status()
    assert not reads
    path = service.settings.data / "corpus" / "expenses.md"
    path.write_bytes(original(path) + b"\nA changed paragraph.")
    assert service.status()["needs_rebuild"] and reads


def test_unexpected_error_is_handled_before_uvicorn_can_log_it(service, monkeypatch, caplog):
    message = "PRIVATE_PROVIDER_REQUEST_CONTENT"

    def fail(*args,**kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(service,"ask",fail)
    # Default TestClient rethrows any exception escaping the ASGI application.
    with TestClient(create_app(service),base_url="http://localhost") as client:
        result = client.post("/api/ask",json={"question":"What receipts are required?"})
        assert result.status_code == 503
        assert client.get("/").headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
    assert "RuntimeError" in caplog.text and message not in caplog.text


def test_redirect_destination_is_checked_before_request():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_corpus.py"
    spec = importlib.util.spec_from_file_location("review2_fetch",module_path)
    fetcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetcher)
    seen=[]

    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302,headers={"location":"http://127.0.0.1/private"})

    with httpx.Client(transport=httpx.MockTransport(redirect),follow_redirects=False) as client:
        with pytest.raises(ValueError,match="HTTPS"):
            fetcher.fetch_page(client,"https://handbook.gitlab.com/start/")
    assert seen == ["https://handbook.gitlab.com/start/"]


def test_challenge_set_remains_locked():
    root = Path(__file__).resolve().parents[1] / "evaluation"
    manifest=json.loads((root / "challenge_manifest.json").read_text())
    content=(root / manifest["file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == manifest["sha256"]
    assert len(json.loads(content)) == 30


@pytest.mark.parametrize("question,expected",[("What is the rule?","clarify"),("What is Jupiter's orbit?","refused")])
def test_refusal_and_clarification_scoring(service, question, expected):
    answer=service.ask(question)
    case={"id":"negative","question":question,"category":"Regression","expected_behavior":expected,
          "expected_sources":[],"evidence_fragments":[]}
    row=score_case(case,answer)
    assert row["behavior_pass"] and row["case_pass"]
    assert row["citation_validity"] is None
    case["expected_behavior"]="answer"
    assert not score_case(case,answer)["behavior_pass"]


@pytest.mark.parametrize("query,bad,good",[
    ("How much is the director paid?", "Do not thank a director for what the company paid.", "The director is paid $90,000 per year."),
    ("What time does the office open?", "Discuss open office work from time to time.", "The office opens at 9am on weekdays."),
])
def test_common_word_overlap_requires_the_requested_value(query,bad,good):
    def hit(text):
        chunk=Chunk(id="value",source_id="value",title="Guide",location="Guide",text=text)
        return SearchHit(chunk=chunk,score=.8,keyword_score=4,vector_score=.7,coverage=1)
    unrelated, actual=hit(bad),hit(good)
    assert not assess_evidence(query,[unrelated],EvidenceProfile([unrelated.chunk]))[0]
    assert assess_evidence(query,[actual],EvidenceProfile([actual.chunk]))[0]


def test_timing_report_labels_the_measured_scope(service):
    from policylens.evaluation import run_evaluation,render_markdown
    folder=service.settings.root / "evaluation"; folder.mkdir()
    (folder / "questions.json").write_text(json.dumps([{"id":"T","question":"What is the rule?",
        "category":"Vague","expected_behavior":"clarify","expected_sources":[],"evidence_fragments":[]}]))
    report=run_evaluation(service)
    assert "excludes HTTP" in report["latency_scope"]
    assert report["session_setup_ms"] >= 0
    assert report["evaluation_wall_ms"] >= report["session_setup_ms"]
    assert "not a faithfulness" in report["citation_metric_kind"]
    assert "excludes HTTP/session setup" in render_markdown(report)

