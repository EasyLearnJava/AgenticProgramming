"""
Ask the IT knowledge base a question: find the closest chunks, then let Gemini answer from them.

Usage:
    python ask.py "How do I fix a VPN timeout?"
    python ask.py                 (then type questions; an empty line quits)
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

HERE = Path(__file__).resolve().parent
STORE_DIR = HERE / "qdrant_data"   # written by ingest.py
COLLECTION = "it_kb"
TOP_K = 3                          # how many chunks to give the model

load_dotenv(HERE / ".env")

if not STORE_DIR.exists():
    sys.exit("No vectors yet. Run first: python ingest.py")

embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")   # the same model ingest.py used
store = QdrantVectorStore.from_existing_collection(embedding=embeddings, path=str(STORE_DIR),
                                                   collection_name=COLLECTION)
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")


def ask(question: str) -> None:
    # 1. Retrieve: embed the question and find the closest chunks
    found = store.similarity_search(question, k=TOP_K)
    context = "\n\n".join(chunk.page_content for chunk in found)

    # 2. Answer: give the model the question and only those chunks
    prompt = (
        "You are an IT help desk assistant. Answer the question using only the context below. "
        "If the context doesn't hold the answer, say you don't know.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    answer = llm.invoke(prompt).text
    print(f"\n{answer}\n")
    print("Sources:", ", ".join(chunk.metadata["title"] for chunk in found), "\n")


if len(sys.argv) > 1:
    ask(" ".join(sys.argv[1:]))
else:
    while question := input("Question (empty line quits): ").strip():
        ask(question)
