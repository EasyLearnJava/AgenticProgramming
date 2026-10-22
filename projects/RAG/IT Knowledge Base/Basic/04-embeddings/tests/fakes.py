"""
Stand-ins for Gemini, for the plain tests: no key, no network, the same result every time.

    KeywordEmbeddings()   ->  each text becomes 11 numbers: how often it uses each keyword below, then its length in
                              words divided by 20. A short question about "vpn" then points closest to the chunks that
                              use "vpn" most for their length. It also notes every call.
"""
from langchain_core.embeddings import Embeddings

KEYWORDS = ["vpn", "mfa", "laptop", "salesforce", "wifi", "password", "printer", "email", "database", "teams"]
SIZE = len(KEYWORDS) + 1     # one number per keyword, plus the length, which also keeps a vector from being all zeros


class KeywordEmbeddings(Embeddings):
    def __init__(self):
        self.calls = []      # in order: ("documents", how many texts) or ("query", the text)

    def _vector(self, text: str) -> list[float]:
        lower = text.lower()
        return [float(lower.count(word)) for word in KEYWORDS] + [len(text.split()) / 20]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(("documents", len(texts)))
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(("query", text))
        return self._vector(text)
