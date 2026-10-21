"""
The user's question, where the app starts answering. The question is embedded with the same model as the chunks, and
Qdrant gives back the chunks whose vectors are closest to it. The retriever, LangChain's standard way to say "give me
the chunks for this question", does both in one call; being a Runnable, it joins a chain with | (step 07).

    embeddings.embed_query("My VPN won't connect")  ->  768 numbers                      (one call to Gemini)
    store.similarity_search_with_score_by_vector(those numbers, k=5)
                                                    ->  [(chunk, 0.81), ...], the 5 closest, closest first
    retriever = make_retriever(store)               k = 5
    retriever.invoke("My VPN won't connect")        ->  the 5 closest chunks, the two steps above in one call
    format_docs(chunks)                             ->  one text with every chunk, numbered and titled, for a prompt

Run it on its own:   python retriever.py                      ->   each step for "How do I fix VPN connection timeouts?"
                     python retriever.py "my email bounced"   ->   each step for your question
Each run makes 3 calls to Gemini: the chunks, then the question twice (by hand, then through the retriever).
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
    question = " ".join(sys.argv[1:]) or QUESTIONS[0]
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)                    # steps 04 and 05: the 28 chunks embedded and stored (one call)
    print(f"Question: {question}")
    # ③ The question becomes a vector, made by the same model as the chunks' vectors, so the two can be compared.
    #    embed_query() tells Gemini this text is a question looking for documents (RETRIEVAL_QUERY). One call.
    question_vector = embeddings.embed_query(question)
    start = ", ".join(f"{x:.4f}" for x in question_vector[:5])
    print(f"The question became {len(question_vector)} numbers: [{start}, ...]")
    # ④ The search. Qdrant compares the question's vector with every stored chunk's vector and gives back the 5
    #    closest, with their scores. The score is the cosine similarity: how closely two vectors point the same way,
    #    from -1 to 1; the closer to 1, the closer the meaning.
    print(f"\nThe {TOP_K} closest chunks, with their scores, closest first:")
    for chunk, score in store.similarity_search_with_score_by_vector(question_vector, k=TOP_K):
        print(f"  {score:.3f}  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    # ⑤ The retriever does ③ and ④ in one call (one more call to Gemini, for the question) and gives back the
    #    chunks, without their scores.
    chunks = make_retriever(store).invoke(question)
    print("\nThe retriever, embedding and searching in one call, found:")
    for chunk in chunks:
        print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    # ⑥ What a prompt will get (step 07): the 2 closest chunks, as one text.
    print("\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):")
    print(format_docs(chunks[:2]))
