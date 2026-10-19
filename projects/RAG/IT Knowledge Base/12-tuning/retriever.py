"""
The retriever: the vector store wrapped as a LangChain Runnable. Give it a question, get back the k closest chunks.
Being a Runnable, it has invoke(), batch() and ainvoke(), and it joins a chain with | (step 07).

    retriever = make_retriever(store)            k = 5
    retriever.invoke("My VPN won't connect")  ->  5 chunks, closest first   (one call: the question's embedding)
    format_docs(chunks)                       ->  one text with every chunk, numbered and titled, for a prompt

Run it on its own:   python retriever.py                      ->   the chunks found for three sample questions
                     python retriever.py "my email bounced"   ->   the chunks found for your question
"""
import sys

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_qdrant import QdrantVectorStore

from models import EMBEDDING_SIZE, embeddings
from vector_store import add_knowledge_base, make_vector_store

TOP_K = 5      # how many chunks each search returns
QUESTIONS = [  # the course app's sample questions
    "How do I fix VPN connection timeouts?",
    "I can't set up MFA on my mobile device",
    "My laptop is running very slow",
]


# ① The retriever. search_kwargs is passed to every search it runs, so each invoke() returns k chunks.
def make_retriever(store: QdrantVectorStore, k: int = TOP_K) -> VectorStoreRetriever:
    return store.as_retriever(search_kwargs={"k": k})


# ② The chunks as one text, for a prompt: each with a number and its article's title, so that an answer can say
#    which article it used.
def format_docs(docs: list[Document]) -> str:
    return "\n\n".join(f"[{number}] {doc.metadata['title']}\n{doc.page_content}" for number, doc in enumerate(docs, 1))


if __name__ == "__main__":
    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    retriever = make_retriever(store)
    # ③ batch(): invoke() once per question, side by side; the lists of chunks come back in the questions' order.
    results = retriever.batch(questions)
    for question, chunks in zip(questions, results):
        print(question)
        for chunk in chunks:
            print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
        print()
    # ④ What a prompt will get for the first question: its two closest chunks, as one text.
    print(format_docs(results[0][:2]))
