"""
A grounded answer: the retriever's chunks and the question go into one prompt, and Gemini answers from those chunks
only. That is RAG: retrieval first, then generation.

    question ──┬──> retriever ─────────────> docs ──┐
               └──> passed through ──────> question ┴─> prompt -> chat model -> parser -> answer

    chain.invoke("How do I fix VPN connection timeouts?")
        ->  {"docs": [5 chunks], "question": "How do I ...?", "answer": "Check that UDP ports 500 and 4500 ..."}
            (a made-up answer: Gemini's words change from run to run)

Run it on its own:   python rag_chain.py                          ->   the answer to the VPN question, and its sources
                     python rag_chain.py "my printer is missing"   ->   the answer to your question
Each run makes three calls to Gemini: the chunks' embeddings, the question's embedding, and the answer.
"""
import sys

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnableParallel, RunnablePassthrough

from models import EMBEDDING_SIZE, chat_model, embeddings
from retriever import format_docs, make_retriever
from vector_store import add_knowledge_base, make_vector_store

QUESTION = "How do I fix VPN connection timeouts?"

# ① The prompt. The system message holds the rules and the chunks ({context}); the human message, the question.
#    "Only the articles below" keeps the answer grounded: without it, the model answers from what it learned in
#    training, which isn't this help desk's knowledge base.
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles below. "
     "If they don't cover the question, say that the knowledge base doesn't cover it. Keep the answer short and "
     "practical, and name the articles you used.\n\nArticles:\n{context}"),
    ("human", "{question}"),
])


# ② The chain. RunnableParallel runs the retriever on the question and passes the question through, side by side,
#    giving {"docs": [...], "question": "..."}. .assign() then adds "answer": the chunks become one text for {context},
#    and the prompt goes to the model, whose reply the parser turns into plain text. Keeping "docs" gives the sources.
def make_rag_chain(retriever: BaseRetriever, model: BaseChatModel) -> Runnable:
    answer = (
        (lambda x: {"context": format_docs(x["docs"]), "question": x["question"]})
        | prompt
        | model
        | StrOutputParser()
    )
    return RunnableParallel(docs=retriever, question=RunnablePassthrough()).assign(answer=answer)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or QUESTION
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    chain = make_rag_chain(make_retriever(store), chat_model)
    # ③ Run it: the retrieval, the prompt and Gemini's answer all happen in this one invoke().
    result = chain.invoke(question)
    print(f"Question: {question}\n")
    print("Answer (Gemini's, from the chunks found):")
    print(result["answer"])
    print("\nSources (the articles of the chunks found, closest first):")
    for title in dict.fromkeys(doc.metadata["title"] for doc in result["docs"]):   # each title once, in order
        print(f"  {title}")
