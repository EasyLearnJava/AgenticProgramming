"""
IT Knowledge Base: A Grounded Answer
====================================

The project's code in one file: it reads the IT knowledge base CSV file into LangChain Documents, cuts them into
chunks, embeds every chunk with Gemini, stores the chunks in Qdrant, in memory, then answers a question from them:
the retriever's chunks and the question go into one prompt, and Gemini is asked to answer from those chunks only.
That is RAG: retrieval first, then generation. It handles:
  1. Reading each article into a Document: its text in page_content, its labels in metadata
  2. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  3. Building Gemini's two models, the embedding model and the chat model, which writes the answers, after config.py
     has checked the API key: no key, no models
  4. Embedding every chunk's text in one call to Gemini
  5. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  6. Making the LangChain store on it, which keeps the embedding model for searches
  7. Storing the chunks with the vectors embed_chunks() made for them: no call to Gemini there
  8. Making a retriever that embeds and searches in one call, and returns TOP_K chunks
  9. Turning the chunks into one numbered, titled text for a prompt
  10. The prompt: the rules and the chunks, then the question
  11. The chain: retriever, prompt, chat model and parser, keeping the chunks found as the sources
  12. Running the steps: main() names them, runs them, then prints the prompt Gemini got, the answer and the sources
      with utils.py's print_answer(); then, for comparison, it asks Gemini the same question alone, with no articles,
      and prints that answer with print_answer_alone()

    question ──┬──> retriever ─────────────> docs ──┐
               └──> passed through ──────> question ┴─> prompt -> chat model -> parser -> answer

Building a model makes no call to Gemini: each embed_... and each invoke does, and uses your key's quota.

Usage:
    python pipeline.py                          # a question only this knowledge base can answer, both ways
    python pipeline.py "my printer is missing"  # your question, both ways (4 calls to Gemini)
"""
import csv
import logging
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnableParallel, RunnablePassthrough
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import MissingKeyError, load_api_key
from utils import print_answer, print_answer_alone

# Found next to this script, whichever folder it's run from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# The text is what gets searched and read; the labels are shown with an answer. The title is in both.
TEXT_COLUMNS = ["title", "problem", "resolution", "notes"]
METADATA_COLUMNS = ["title", "system", "category", "priority", "tags"]

# In characters: the articles are 569 to 716 characters long, so 512 makes 2 or 3 chunks each (28 in all)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# gemini-embedding-001 gives 128 to 3072 numbers per text; 768 is a size Google recommends, and cheaper to store
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768
CHAT_MODEL = "gemini-3.5-flash-lite"    # small, fast and cheap
MAX_OUTPUT_TOKENS = 500                 # a cap on each answer's length, and so on its cost

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"

TOP_K = 5      # how many chunks each search returns
QUESTIONS = [  # the course app's sample questions
    "How do I fix VPN connection timeouts?",
    "I can't set up MFA on my mobile device",
    "My laptop is running very slow",
]

# Only this knowledge base knows the answer: the WiFi article's notes say Building C's upgrade is due in Q2
QUESTION = "When will the access points in Building C be upgraded?"


class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores which file to read, and reads nothing
    Step 2: Load: lazy_load() reads the file, one Document per row (load() collects them into a list)
    """

    def __init__(self, path: Path = KB_FILE):
        self.path = path

    def lazy_load(self) -> Iterator[Document]:
        """Yield one Document per row: "Title: ..." blocks as the text, and the labels as metadata."""
        with open(self.path, encoding="utf-8", newline="") as file:
            # DictReader comes from Python's csv module: each row as {column: value}, named by the header row
            for number, row in enumerate(csv.DictReader(file)):
                # Each part keeps its label, so the model can tell the symptom from the fix
                text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
                metadata = {"doc_id": str(number), **{column: row[column] for column in METADATA_COLUMNS}}
                # Document comes from langchain_core: LangChain's text (page_content) with its labels (metadata)
                yield Document(page_content=text, metadata=metadata)


def load_documents(path: Path = KB_FILE) -> list[Document]:
    """Every article, as a list of Documents."""
    # load() comes from LangChain's BaseLoader, which KBLoader extends: lazy_load()'s Documents, in a list
    return KBLoader(path).load()


def make_splitter(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    """A splitter that breaks at empty lines first, then line breaks, then spaces; it records start_index."""
    # RecursiveCharacterTextSplitter comes from langchain_text_splitters: LangChain's splitter by size
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True)


def split_documents(docs: list[Document], chunk_size: int = CHUNK_SIZE,
                    chunk_overlap: int = CHUNK_OVERLAP) -> list[Document]:
    """Every Document cut into chunks, each a new Document with a copy of its article's metadata."""
    return make_splitter(chunk_size, chunk_overlap).split_documents(docs)


# Google's library warns once a run that "automatic function calling" is "not recommended": a feature this project
# never uses. The warning would look like a problem, so only that one message is dropped; any other still shows.
# getLogger() and addFilter() come from Python's logging module: a filter that returns False drops the message
logging.getLogger("google_genai.models").addFilter(
    lambda record: "automatic function calling" not in record.getMessage())

try:
    api_key = load_api_key()
except MissingKeyError as err:
    # exit() comes from Python's sys module: it stops the program with this message
    sys.exit(f"Can't build the models: {err}")

# embed_documents() embeds texts as documents to be found, embed_query() as a question looking for them
# GoogleGenerativeAIEmbeddings comes from langchain_google_genai: LangChain's class for Gemini's embeddings
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key,
                                          output_dimensionality=EMBEDDING_SIZE)

# No temperature: gemini-3.5-flash-lite has fixed sampling, and LangChain drops one given to it, with a warning
# ChatGoogleGenerativeAI comes from langchain_google_genai: LangChain's class for Gemini's chat models
chat_model = ChatGoogleGenerativeAI(model=CHAT_MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)


def embed_chunks(chunks: list[Document], embeddings: Embeddings) -> list[list[float]]:
    """One vector per chunk, from one embed_documents() call. Only the text is embedded, not the metadata."""
    # embed_documents() comes from LangChain's Embeddings (Gemini's, here): a list of texts in, a vector each out
    return embeddings.embed_documents([chunk.page_content for chunk in chunks])


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a new, empty collection of `size`-number vectors; in memory if no client."""
    # QdrantClient comes from qdrant_client: ":memory:" runs Qdrant inside this program, in memory
    client = client if client is not None else QdrantClient(":memory:")
    # Always fresh: a collection already there by this name is deleted, so nothing from before is left in it
    # collection_exists() comes from qdrant_client's QdrantClient: whether a collection by this name is there
    if client.collection_exists(collection):
        # delete_collection() comes from qdrant_client's QdrantClient: it removes the collection and its points
        client.delete_collection(collection)
    # create_collection() and VectorParams come from qdrant_client: a new collection, its vector size and distance
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # The check would embed a sample text (one more call to Gemini); the collection was just made with the right size
    # QdrantVectorStore comes from langchain_qdrant: LangChain's vector store on a Qdrant collection
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


def store_vectors(store: QdrantVectorStore, chunks: list[Document], vectors: list[list[float]]) -> None:
    """Store each chunk as one point: the vector embed_chunks() made for it, its text and its labels; nothing is
    embedded here. A chunk without a vector, or a vector without a chunk, stops it: no chunk is left out."""
    # The text and labels go under "page_content" and "metadata", the names LangChain's store reads them from
    # PointStruct comes from qdrant_client, uuid4() from Python's uuid module: one point, with a new random id
    points = [PointStruct(id=str(uuid.uuid4()), vector=vector,
                          payload={"page_content": chunk.page_content, "metadata": chunk.metadata})
              for chunk, vector in zip(chunks, vectors, strict=True)]     # strict: the two lists, the same length
    # upsert() comes from qdrant_client's QdrantClient: it writes the points into the collection
    store.client.upsert(store.collection_name, points=points)


def make_retriever(store: QdrantVectorStore, k: int = TOP_K) -> VectorStoreRetriever:
    """A retriever whose every invoke() returns the k closest chunks."""
    # as_retriever() comes from LangChain's VectorStore: a retriever that searches this store
    return store.as_retriever(search_kwargs={"k": k})


def format_docs(docs: list[Document]) -> str:
    """The chunks as one text for a prompt, each numbered and titled so an answer can name its article."""
    return "\n\n".join(f"[{number}] {doc.metadata['title']}\n{doc.page_content}" for number, doc in enumerate(docs, 1))


# "Only the articles below" asks Gemini to answer from the chunks found, not from what it learned in training.
# Models mostly do as asked, but nothing here checks it: RAG makes made-up answers rarer, not impossible.
# from_messages() comes from LangChain's ChatPromptTemplate: a prompt made of these messages
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles below. "
     "If they don't cover the question, say that the knowledge base doesn't cover it. Keep the answer short and "
     "practical, and name the articles you used.\n\nArticles:\n{context}"),
    ("human", "{question}"),
])


def make_rag_chain(retriever: BaseRetriever, model: BaseChatModel) -> Runnable:
    """The chain: question -> {"docs": the chunks found, "question": ..., "answer": Gemini's answer}."""
    answer = (
        (lambda x: {"context": format_docs(x["docs"]), "question": x["question"]})
        | prompt
        | model
        # StrOutputParser comes from langchain_core: it turns the model's reply into plain text
        | StrOutputParser()
    )
    # Retrieve and pass the question through side by side, then add the answer, keeping "docs" for the sources
    # RunnableParallel, RunnablePassthrough and assign() come from LangChain (langchain_core.runnables)
    return RunnableParallel(docs=retriever, question=RunnablePassthrough()).assign(answer=answer)


# The tests pass stand-ins for Gemini as `embeddings` and `model`, with the embeddings' vector size
def main(question: str = QUESTION, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
         size: int = EMBEDDING_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    vectors = embed_chunks(chunks, embeddings)     # one call to Gemini: every chunk's embedding
    print(f"Step 3: Embed: {len(vectors)} vectors of {len(vectors[0])} numbers")
    store = make_vector_store(embeddings, size)
    store_vectors(store, chunks, vectors)          # Step 3's vectors: no call to Gemini
    # count() comes from qdrant_client's QdrantClient: how many points the collection holds
    print(f"Step 4: Store: {store.client.count(store.collection_name).count} points, in Qdrant in memory")
    print("Step 5: Retrieve and answer")
    chain = make_rag_chain(make_retriever(store), model)
    # invoke() comes from LangChain's Runnable: it runs the whole chain on one input
    result = chain.invoke(question)                # retrieval, prompt and answer, all in this one call
    # What Gemini got: the chain's own prompt, filled in with the chunks it found and the question
    # format_messages() comes from LangChain's ChatPromptTemplate: the prompt's messages, filled in
    messages = prompt.format_messages(context=format_docs(result["docs"]), question=question)
    print_answer(question, messages, result)
    # For comparison: the same question to Gemini alone, with no retriever and no articles (one more call)
    # StrOutputParser comes from langchain_core: it turns the model's reply into plain text
    print_answer_alone((model | StrOutputParser()).invoke(question))


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or QUESTION)
