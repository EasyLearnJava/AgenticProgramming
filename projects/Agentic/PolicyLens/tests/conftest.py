"""Fixtures use tiny local documents; tests never call a hosted model."""

import json
from datetime import datetime, timezone

import pytest

from policylens.config import Settings
from policylens.service import PolicyService


@pytest.fixture
def service(tmp_path):
    corpus = tmp_path / "data" / "corpus"
    corpus.mkdir(parents=True)
    entries = []
    for name, title, text in [
        ("expenses", "Expense Policy", "# Expense Policy\n\n## Receipts\n\nReceipts are required for expenses over $50. Expense claims over 90 days require manager approval.\n"),
        ("security", "Security Policy", "# Security Policy\n\n## Credentials\n\nNever share passwords in chat. Use 1Password to manage unique credentials. The security code is SEC-101.\n"),
    ]:
        (corpus / f"{name}.md").write_text(text, encoding="utf-8")
        entries.append({"source_id": name, "title": title, "file": f"{name}.md", "category": "Test",
                        "fetched_at": datetime.now(timezone.utc).isoformat(), "url": "https://example.com/policy"})
    (corpus / "sources.json").write_text(json.dumps(entries), encoding="utf-8")
    svc = PolicyService(Settings(root=tmp_path))
    svc.rebuild()
    return svc

