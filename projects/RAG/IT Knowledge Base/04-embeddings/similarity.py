"""
Embeddings: the 10 articles and a question turned into vectors by Gemini, and the articles ranked by how close their
vector is to the question's. Close vectors mean close meanings, so this finds articles by meaning, not by shared words.

    rank("My VPN won't connect", docs, embeddings)  ->  [(0.78, "VPN Connection Timeout"), (0.62, ...), ...]
                                                        (made-up scores: Gemini's numbers decide the real ones)

Run it on its own:   python similarity.py                          ->   the ranking for "My VPN won't connect"
                     python similarity.py "my laptop is so slow"   ->   the ranking for your question
Each run makes two calls to Gemini: one for the 10 articles, one for the question.
"""
import math
import sys

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from knowledge_base import load_documents
from models import EMBEDDING_MODEL, EMBEDDING_SIZE, embeddings

QUESTION = "My VPN won't connect"


# ① How close two vectors point, from -1 to 1: 1 means the same direction (the same meaning), 0 means unrelated.
#    It's their dot product divided by both lengths, so only the directions count, not the lengths.
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


# ② Embed every article and the question, then sort the articles by how close they are to the question, closest
#    first. Only the articles' texts (page_content) are embedded; the titles come from their metadata.
def rank(question: str, docs: list[Document], embeddings: Embeddings) -> list[tuple[float, str]]:
    article_vectors = embeddings.embed_documents([doc.page_content for doc in docs])   # one call, every article
    question_vector = embeddings.embed_query(question)                                 # one call, the question
    scores = [(cosine_similarity(question_vector, vector), doc.metadata["title"])
              for doc, vector in zip(docs, article_vectors)]
    return sorted(scores, reverse=True)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or QUESTION
    # ③ Rank the articles for the question: this is where the two calls to Gemini happen.
    ranking = rank(question, load_documents(), embeddings)
    print(f"Each text became {EMBEDDING_SIZE} numbers ({EMBEDDING_MODEL}).")
    print(f"The articles, closest to {question!r} first:")
    for score, title in ranking:
        print(f"  {score:.3f}  {title}")
