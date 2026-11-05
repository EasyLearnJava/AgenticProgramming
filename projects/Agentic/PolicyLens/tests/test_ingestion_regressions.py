"""Check real PDF parsing and the HTML structures called out in review."""

import hashlib
import importlib.util
import json
from io import BytesIO
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from policylens.api import create_app


def fetch_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_corpus.py"
    spec = importlib.util.spec_from_file_location("corpus_fetcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_html_keeps_nested_list_leadins_and_table_paragraphs():
    fetcher = fetch_module()
    html = '''<main><h1>Equipment</h1>
    <ul><li>Parent eligibility rule<ul><li><p>Child receipt requirement</p></li></ul></li></ul>
    <table><tr><th><p>Category</p></th><th>Amount</th></tr>
    <tr><td><p>Laptop repair</p></td><td><p>500 USD</p></td></tr></table>
    <p>''' + "Ordinary handbook context. " * 15 + "</p></main>"
    text = fetcher.extract_content(html, "Equipment")
    for phrase in ["Parent eligibility rule", "Child receipt requirement", "Laptop repair", "500 USD"]:
        assert text.count(phrase) == 1
    assert "Category | Amount" in text


def test_corpus_manifest_hashes_the_written_bytes(tmp_path, monkeypatch):
    fetcher = fetch_module()
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    monkeypatch.setattr(fetcher, "SOURCES", [("sample", "Sample", "Test", "https://handbook.gitlab.com/sample/")])
    html = "<main><h1>Sample</h1><p>" + "Handbook paragraph. " * 30 + "</p></main>"
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html))
    monkeypatch.setattr(fetcher.httpx, "Client", lambda **kwargs: real_client(transport=transport))
    fetcher.main()
    folder = tmp_path / "data" / "corpus"
    doc = json.loads((folder / "sources.json").read_text(encoding="utf-8"))[0]
    content = (folder / doc["file"]).read_bytes()
    assert b"\r\n" not in content
    assert hashlib.sha256(content).hexdigest() == doc["sha256"]


def test_successful_pdf_upload_keeps_page_and_text(service):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 170 Td (Laptop repair allowance requires an itemized receipt.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    with TestClient(create_app(service), base_url="http://localhost") as client:
        uploaded = client.post("/api/documents", files={"file": ("repairs.pdf", buffer.getvalue(), "application/pdf")})
        assert uploaded.status_code == 200
        source_id = Path(uploaded.json()["file"]).stem
        assert "Laptop repair allowance" in client.get("/api/documents/" + source_id).json()["text"]
        assert client.post("/api/index").status_code == 200
        answer = client.post("/api/ask", json={"question": "What receipt does the laptop repair allowance require?",
                                             "source_ids": [source_id]}).json()
        assert answer["status"] == "evidence" and answer["citations"]
        assert all("Page 1" in citation["location"] for citation in answer["citations"])

