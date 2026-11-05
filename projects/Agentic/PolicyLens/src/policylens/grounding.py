"""Information-weighted lexical evidence checks, with a permissive neural path.

Rare query terms carry more weight than ubiquitous words. Candidate terms must
co-occur in a short passage; finding them somewhere in five documents is not enough.
This is a lexical fallback, not a semantic answerability or entailment guarantee.
"""

import math
import re
from collections import Counter

from policylens.models import SearchHit
from policylens.text import canonical_text, expand_contractions, stem, tokens

# Shared across ambiguity, scope checks and extraction. These are conversational
# operators, never product names, places or evaluation-answer vocabulary.
_OPERATORS = {stem(word) for word in """need happen mean meaning definition difference describe
detail example work use guidance cover role help find say know get like explain tell
rule policy process procedure benefit information thing something anything situation""".split()}


def terms(text: str) -> set[str]:
    # "What time" asks for a value type; time is not a subject qualifier here.
    text = re.sub(r"\bwhat time\b", "", expand_contractions(text))
    words = set(tokens(text)) - _OPERATORS
    # A retained compound token is redundant with its split words, except exact codes.
    return {word for word in words if "-" not in word or any(char.isdigit() for char in word)}


def body_text(text: str) -> str:
    return re.sub(r"(?m)^#{1,6}\s+[^\n]*(?:\n|$)", "", text)


def is_ambiguous(question: str) -> bool:
    return not terms(question)


def request_issue(question: str) -> str | None:
    text = expand_contractions(question).strip()
    if (re.match(r"^(?:please\s+)?ignore\b.{0,90}\b(?:instructions?|handbook|evidence|sources?)\b", text)
            or re.match(r"^(?:please\s+)?(?:invent|fabricate|make up)\b.{0,60}\b(?:policy|answer|approval|rule)\b", text)):
        return "The request asks to bypass or invent source evidence."
    navigation = re.match(r"^(?:where|how can|how do|how to)\b", text)
    if not navigation and (re.search(r"\bmy\b.{0,35}\b(?:balance|salary|paycheck|reimbursement status)\b", text)
                           or re.search(r"^how (?:many|much)\b.*\bi have\b.*\b(?:left|remaining)\b", text)):
        return "The documents do not contain personal employee records."
    if re.match(r"^what (?:is|are)\b.*\b(?:password|pin|secret|api key)\s+(?:for|of|to)\b", text):
        return "Credential-management policies do not contain account secrets."
    return None


class EvidenceProfile:
    """Built once per index generation and reused by retrieval and extraction."""
    def __init__(self, chunks):
        self.count = max(len(chunks), 1)
        self.frequency = Counter()
        self.windows = {}
        self.window_text = {}
        self.context = {}
        self.named_topics = set()
        self.retrieval_tokens = {}
        for chunk in chunks:
            for name in re.findall(r"\b[A-Z][A-Z0-9]{1,}(?:-[A-Z0-9]+)?\b", chunk.title + " " + chunk.location + " " + chunk.text):
                self.named_topics.update(terms(name))
            self.retrieval_tokens[chunk.id] = tokens(chunk.text + " " + chunk.title + " " + chunk.location)
            body = body_text(chunk.text)
            context = terms(chunk.title + " " + chunk.location)
            self.context[chunk.id] = context
            self.frequency.update(terms(body) | context)
            windows = []
            raw_windows = []
            for paragraph in re.split(r"\n\s*\n", body):
                words = paragraph.split()
                for start in range(0, len(words), 40):
                    raw = " ".join(words[start:start + 80])
                    windows.append(terms(raw))
                    raw_windows.append(raw)
            self.windows[chunk.id] = windows
            self.window_text[chunk.id] = raw_windows

    def idf(self, term: str) -> float:
        return math.log1p((self.count + 1) / (self.frequency[term] + 1))

    def weighted_coverage(self, requested: set[str], available: set[str]) -> float:
        return sum(self.idf(t) for t in requested & available) / max(sum(self.idf(t) for t in requested), 1e-9)


def assess_evidence(question: str, hits: list[SearchHit], profile: EvidenceProfile | None = None,
                    mode: str = "extractive") -> tuple[bool, str]:
    if not hits:
        return False, "No candidate passages were retrieved."
    profile = profile or EvidenceProfile([hit.chunk for hit in hits])
    requested = terms(question)
    if not requested:
        return False, "A specific topic is needed."
    windows = [(window, window | profile.context[hit.chunk.id], raw)
               for hit in hits for window, raw in zip(profile.windows.get(hit.chunk.id, []),
                                                      profile.window_text.get(hit.chunk.id, []))]
    if not windows:
        return False, "The candidates contain no body evidence."
    available = set().union(*(context for body, context, raw in windows))
    coverage = profile.weighted_coverage(requested, available)
    if mode == "openai":
        # Lexical uncertainty must not veto a neural model's paraphrase reasoning.
        plausible = coverage >= 0.15 or max(hit.vector_score for hit in hits) >= 0.2
        return plausible, "Semantic answerability and claim support are delegated to the model checks."
    # A "who" question about an explicitly named subject can be supported by a
    # named person/role in that subject's body, even when the verb is paraphrased.
    named = requested & profile.named_topics if re.match(r"\s*who\b", question, re.IGNORECASE) else set()
    if named:
        requested = named
        coverage = profile.weighted_coverage(requested, available)
    needed = 1 if len(requested) == 1 else 2
    # Headings may supply the subject of a body clause, but never an answer value.
    # A question asking for a time, amount or phone number needs that value in body text.
    text = expand_contractions(question)
    slot = r"\b[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]+){0,3}\b" if named else None
    if re.search(r"\bhow much\b", text):
        slot = r"(?:[$€£]\s*\d|\b\d[\d,.]*\s*(?:usd|dollars?|eur|gbp|percent|%))"
    elif re.search(r"\bwhat time\b", text):
        slot = r"\b(?:\d{1,2}:\d{2}|\d{1,2}\s*(?:am|pm)|noon|midnight)\b"
    elif re.search(r"\bphone number\b", text):
        slot = r"(?<!\d)\+?\d[\d ()-]{6,}\d(?!\d)"
    local = [context for body, context, raw in windows
             if (requested & body or named & context) and len(requested & context) >= needed
             and (slot is None or (requested <= context and re.search(slot, raw, 0 if named else re.IGNORECASE)))]
    specific = any(profile.frequency[term] <= max(1, profile.count / 3) for term in requested & available)
    specific = specific or bool(slot and local)  # An explicit matching answer value is informative too.
    cooccurrence = max((profile.weighted_coverage(requested, window) for window in local), default=0)
    supported = coverage >= 0.60 and cooccurrence >= 0.40 and specific
    return supported, (f"Weighted body coverage {coverage:.2f}; local co-occurrence {cooccurrence:.2f}; "
                       f"specific anchor {'present' if specific else 'absent'}. Lexical heuristic, not semantic proof.")

