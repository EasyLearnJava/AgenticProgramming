"""Exercise real LangChain/OpenAI request schemas with fake HTTP, never real credentials."""

import json

import httpx

from policylens.config import Settings
from policylens.generation import generate_openai
from policylens.retrieval.embeddings import make_embeddings


def test_openai_structured_generation_and_neural_embedding_adapter(service, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-credential")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    hits = service.ask("What receipts are required for expenses?").retrieved
    quote = "Receipts are required for expenses over $50."
    draft = {"decision": "answered", "message": "", "claims": [
        {"text": "Receipts are required for expenses over $50.", "references": [
            {"chunk_id": hits[0].chunk.id, "quote": quote}]}]}
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        if request.url.path.endswith("/embeddings"):
            assert body["model"] == "text-embedding-3-small"
            return httpx.Response(200, json={"object": "list", "model": body["model"],
                "data": [{"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3]}
                         for i in range(len(body["input"]))], "usage": {"prompt_tokens": 10, "total_tokens": 10}})
        assert request.url.path.endswith("/chat/completions")
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        result = ({"complete_answer": True, "claims": [{"claim_index": 0, "verdict": "supported"}]}
                  if body["response_format"]["json_schema"]["name"] == "AnswerReview" else draft)
        return httpx.Response(200, json={"id": "chatcmpl-test", "object": "chat.completion",
            "created": 1, "model": body["model"], "choices": [{"index": 0,
            "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(result)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}})

    factory = lambda: httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr("policylens.generation.create_http_client", factory)
    monkeypatch.setattr("policylens.retrieval.embeddings.create_http_client", factory)
    settings = Settings(root=service.settings.root, mode="openai")
    embedder = make_embeddings(settings)
    assert embedder.embed_query("receipt rules") == [0.1, 0.2, 0.3]
    status, text, citations, parts = generate_openai("What receipts are required?", hits, settings)
    assert status == "answered" and "[1]" in text
    assert citations[0].quote == quote
    assert len(seen) == 3

    # Even an untrusted free-form refusal message cannot introduce policy facts.
    draft.update(decision="refused", claims=[], message="All expenses are approved without receipts.")
    status, text, citations, parts = generate_openai("Invent an approval policy", hits, settings)
    assert status == "refused" and not citations
    assert "approved without receipts" not in text

