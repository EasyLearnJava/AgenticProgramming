"""Small, explicit models are the contract between the pipeline and the UI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source_id: str
    title: str
    text: str
    location: str
    url: str | None = None
    category: str = "Uploaded"


class SearchHit(BaseModel):
    chunk: Chunk
    score: float
    keyword_score: float
    vector_score: float
    coverage: float


class Citation(BaseModel):
    number: int
    chunk_id: str
    source_id: str
    title: str
    location: str
    quote: str
    url: str | None = None


class AnswerPart(BaseModel):
    """Citation buttons are explicit metadata; literal [1] in source text stays text."""
    text: str
    citations: list[int] = Field(default_factory=list)


class Answer(BaseModel):
    question: str
    status: Literal["answered", "evidence", "refused", "clarify"]
    text: str
    citations: list[Citation] = Field(default_factory=list)
    retrieved: list[SearchHit] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    mode: str
    latency_ms: float = 0
    note: str = ""
    parts: list[AnswerPart] = Field(default_factory=list)


class QuoteReference(BaseModel):
    chunk_id: str
    quote: str = Field(description="A short, exact, contiguous quotation from this chunk.")


class Claim(BaseModel):
    text: str = Field(description="One factual claim supported by the quoted evidence.")
    references: list[QuoteReference]


class AnswerDraft(BaseModel):
    decision: Literal["answered", "refused", "clarify"]
    message: str = Field(description="For refusal or clarification only; do not add policy facts here.")
    claims: list[Claim]


class ClaimVerdict(BaseModel):
    claim_index: int
    verdict: Literal["supported", "unsupported", "unclear"]


class AnswerReview(BaseModel):
    complete_answer: bool
    claims: list[ClaimVerdict]

