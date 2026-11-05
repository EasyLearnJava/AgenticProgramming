"""An explicit LangGraph: retrieve → assess → answer/refuse/clarify → finish.

Each node has one responsibility. Trace entries show what happened and how long
it took without exposing API keys or chain-of-thought.
"""

from time import perf_counter
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from policylens.config import Settings
from policylens.generation import extract_evidence, generate_openai, is_ambiguous
from policylens.grounding import assess_evidence, request_issue
from policylens.models import Answer, SearchHit
from policylens.retrieval.hybrid import search
from policylens.retrieval.store import QuerySession


class RagState(TypedDict, total=False):
    question: str
    source_ids: list[str]
    hits: list[SearchHit]
    trace: list[dict]
    route: str
    result: Answer
    session: QuerySession
    issue: str | None


def build_pipeline(settings: Settings, embeddings):
    def retrieve(state: RagState):
        started = perf_counter()
        issue = request_issue(state["question"])
        if issue or is_ambiguous(state["question"]):
            return {"hits": [], "issue": issue, "trace": [{"step": "Retrieve", "ms": 0,
                    "detail": issue or "Skipped: clarification needed"}]}
        session = state["session"]
        chunks, matrix, metadata = session.chunks, session.matrix, session.metadata
        if metadata.get("identity") != settings.index_identity:
            raise ValueError("Index settings changed or index is empty. Rebuild the index first.")
        vector = embeddings.embed_query(state["question"])
        hits = search(state["question"], chunks, matrix, vector, settings.candidates,
                      settings.top_k, state.get("source_ids"), session.profile)
        detail = f"BM25 + vector search → RRF → lexical rerank → {len(hits)} chunks"
        return {"hits": hits, "trace": [{"step": "Retrieve", "ms": round((perf_counter() - started) * 1000, 1),
                                        "detail": detail}]}

    def assess(state: RagState):
        if state.get("issue"):
            route, detail = "refuse", state["issue"]
        elif is_ambiguous(state["question"]):
            route, detail = "clarify", "Question needs a specific topic"
        else:
            supported, detail = assess_evidence(state["question"], state["hits"], state["session"].profile, settings.mode)
            route = "answer" if supported else "refuse"
        return {"route": route, "trace": state["trace"] + [{"step": "Assess", "ms": 0, "detail": detail}]}

    def answer(state: RagState):
        started = perf_counter()
        try:
            if settings.mode == "openai":
                status, text, citations, parts = generate_openai(state["question"], state["hits"], settings)
                note = "Quoted passages and claim support checked automatically. The model check can err; inspect the sources."
            else:
                status, text, citations, parts = extract_evidence(state["question"], state["hits"], state["session"].profile)
                note = "Extractive preview: verbatim passages, lexical vectors, no LLM or semantic embeddings."
        except ValueError:
            status, text, citations, parts = "refused", "The answer did not pass citation validation. Please check the retrieved sources.", [], []
            note = "An unverified answer was withheld."
        trace = state["trace"] + [{"step": "Generate" if settings.mode == "openai" else "Extract",
                                   "ms": round((perf_counter() - started) * 1000, 1),
                                   "detail": f"{len(citations)} validated source quotations"}]
        return {"result": Answer(question=state["question"], status=status, text=text,
                                 citations=citations, retrieved=state["hits"], trace=trace,
                                 mode=settings.mode, note=note, parts=parts)}

    def stop(state: RagState):
        clarify = state["route"] == "clarify"
        message = ("Which policy or situation do you mean? Try asking about expenses, time off, passwords or communication."
                   if clarify else "I could not find enough evidence in the indexed documents. Try a more specific question or add the relevant policy.")
        return {"result": Answer(question=state["question"], status="clarify" if clarify else "refused",
                                 text=message, retrieved=state["hits"], trace=state["trace"], mode=settings.mode)}

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("assess", assess)
    graph.add_node("answer", answer)
    graph.add_node("stop", stop)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "assess")
    graph.add_conditional_edges("assess", lambda state: state["route"],
                               {"answer": "answer", "refuse": "stop", "clarify": "stop"})
    graph.add_edge("answer", END)
    graph.add_edge("stop", END)
    return graph.compile()

