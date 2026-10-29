"""
Stand-ins for the providers, for the plain tests: no key, no network, the same result every time.

    KeywordEmbeddings()        ->  each text becomes 11 numbers: how often it uses each keyword below, then its length
                                   in words divided by 20. A short question about "vpn" then points closest to the
                                   chunks that use "vpn" most for their length. It also notes every call.
    reply("text", ...)         ->  a chat model's reply, with the token counts and finish reason Gemini reports
    FakeGenaiClient(...)       ->  Google's own client, faked at the methods LangChain's Gemini classes call, so the
                                   real classes run end to end without a network: each method returns what it's
                                   given, or raises it
"""
from types import SimpleNamespace

from google.genai import types
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage

KEYWORDS = ["vpn", "mfa", "laptop", "salesforce", "wifi", "password", "printer", "email", "database", "teams"]
SIZE = len(KEYWORDS) + 1     # one number per keyword, plus the length, which also keeps a vector from being all zeros
ANSWER = "Open UDP ports 500 and 4500."


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


def reply(text: str, *, input_tokens: int = 950, output_tokens: int = 12, finish_reason: str = "STOP") -> AIMessage:
    """A chat model's reply, as LangChain's Gemini class gives it back."""
    return AIMessage(content=text, response_metadata={"finish_reason": finish_reason},
                     usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens,
                                     "total_tokens": input_tokens + output_tokens})


def gemini_answer(text: str, finish_reason: str = "STOP") -> types.GenerateContentResponse:
    """What Google's client returns for one generate_content call."""
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]),
                                    finish_reason=finish_reason)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=950, candidates_token_count=12,
                                                                  total_token_count=962),
        model_version="gemini-3.5-flash-lite")


class FakeGenaiClient:
    """Google's client with its two methods faked: generate_content (chat) and embed_content (embeddings).

    generate: a GenerateContentResponse to return, or an exception to raise
    embed: a function from a text to its vector, or an exception to raise
    """

    def __init__(self, *, generate=None, embed=None):
        self.generate, self.embed = generate, embed
        self.models = SimpleNamespace(generate_content=self._generate, embed_content=self._embed)
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._agenerate,
                                                          embed_content=self._aembed))

    def _generate(self, **request):
        if isinstance(self.generate, BaseException):
            raise self.generate
        return self.generate

    async def _agenerate(self, **request):
        return self._generate(**request)

    def _embed(self, *, contents, **request):
        if isinstance(self.embed, BaseException):
            raise self.embed
        texts = [content["parts"][0]["text"] for content in contents] if isinstance(contents, list) else [contents]
        return types.EmbedContentResponse(embeddings=[types.ContentEmbedding(values=self.embed(text))
                                                      for text in texts])

    async def _aembed(self, **request):
        return self._embed(**request)
