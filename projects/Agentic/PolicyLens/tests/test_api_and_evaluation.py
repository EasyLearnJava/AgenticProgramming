"""HTTP boundaries and metric definitions are part of the app's behavior."""

from fastapi.testclient import TestClient

from policylens.api import create_app
from policylens.evaluation import score_case


def test_http_flow_and_input_boundaries(service):
    with TestClient(create_app(service), base_url="http://localhost") as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
        assert not client.get("/api/status").json()["needs_rebuild"]
        result = client.post("/api/ask", json={"question": "What receipts are required?"})
        assert result.status_code == 200
        assert result.json()["citations"]
        assert client.post("/api/ask", json={"question": "x" * 1501}).status_code == 422
        assert client.post("/api/ask", json={"question": "   "}).status_code == 400
        assert client.post("/api/index", headers={"Origin": "https://unrelated.example"}).status_code == 403
        assert client.get("/api/documents/missing").status_code == 404
        assert client.get("/api/reports/not-a-report.json").status_code == 404
        invalid = client.post("/api/documents", files={"file": ("bad.exe", b"data")})
        assert invalid.status_code == 400
        uploaded = client.post("/api/documents", files={"file": ("guide.txt", b"This handbook describes working hours and core collaboration.")})
        assert uploaded.status_code == 200
        assert client.get("/api/status").json()["needs_rebuild"]
        assert client.post("/api/index").status_code == 200
        assert not client.get("/api/status").json()["needs_rebuild"]


def test_retrieval_metrics_are_separate_from_faithfulness(service):
    answer = service.ask("What receipts are required for expenses?")
    case = {"id": "T1", "category": "Test", "question": answer.question,
            "expected_sources": ["expenses"], "expected_behavior": "answer",
            "evidence_fragments": ["Receipts are required for expenses over $50"]}
    row = score_case(case, answer)
    assert row["source_recall_at_k"] == 1
    assert row["reference_evidence_recall"] == 1
    assert row["citation_validity"] == 1
    assert row["human_review"]["faithful_claims"] is None
    assert "faithfulness" not in row

