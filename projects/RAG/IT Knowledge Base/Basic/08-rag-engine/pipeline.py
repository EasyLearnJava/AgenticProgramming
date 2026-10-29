"""
IT Knowledge Base: The RAG Engine
=================================

The project's code in one file: the whole pipeline in one class, the way a server uses it. build() is the ingestion
half, run once: read, chunk, embed and store. query() is the query half, run for each question: retrieve, then
answer. It handles:
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
  11. The engine's build: load and split the articles, embed and store the chunks, make the retriever (one call to
      Gemini)
  12. The engine's answer to one question: the retriever finds the chunks, the prompt is filled in with them and the
      question, and Gemini answers it; up to MAX_SOURCES different articles among the chunks go with it, as sources
  13. The engine's stats: what it holds and how it's set up
  14. Running the steps: main() builds the engine, names the steps, then prints each answer with utils.py's
      print_result()

    question -> retriever -> found (the chunks) ──┐
    question ─────────────────────────────────────┴─> prompt -> chat model -> parser -> answer

Building a model makes no call to Gemini: each embed_... and each invoke does, and uses your key's quota.

    engine = RAGEngine()      ->  settings only: nothing is read and no call is made
    engine.build()            ->  read, chunk, embed and store (one call to Gemini)
    engine.query(question)    ->  the answer and up to 3 sources (two calls)

Usage:
    python pipeline.py                       # answers to the three sample questions
    python pipeline.py "printer not found"   # the answer to your question
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
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import MissingKeyError, load_api_key
from utils import print_result

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

# Sources per answer: the first 3 different articles among the chunks the search found. They're what Gemini was
# given, not a checked list of what its answer used: an answer can use fewer, or none.
MAX_SOURCES = 3
SNIPPET_LENGTH = 200   # characters of each source's text shown with it

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



class RAGEngine:
    """
    The RAG pipeline as one object.

    Step 1: Configure: the constructor stores the settings; nothing is read and no call is made
    Step 2: Build: build() loads, splits, embeds and stores the articles, and makes the retriever
    Step 3: Answer: query() answers one question with its sources
    """

    # Every setting has a default and is passed by name (the *); the tests pass stand-ins for Gemini
    def __init__(self, *, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
                 embedding_size: int = EMBEDDING_SIZE, client: QdrantClient | None = None,
                 data_path: str | Path = KB_FILE, collection: str = COLLECTION,
                 chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, top_k: int = TOP_K):
        self.embeddings, self.model, self.embedding_size, self.client = embeddings, model, embedding_size, client
        # Path comes from Python's pathlib: a file path that works the same on every system
        self.data_path, self.collection = Path(data_path), collection
        self.chunk_size, self.chunk_overlap, self.top_k = chunk_size, chunk_overlap, top_k
        self.documents, self.chunks = [], []
        self.retriever: VectorStoreRetriever | None = None
        # The models' names, for stats(): Gemini's models know theirs (.model); a stand-in goes by its class name
        self.embedding_model_name = getattr(embeddings, "model", type(embeddings).__name__)
        self.chat_model_name = getattr(model, "model", type(model).__name__)

    def build(self) -> None:
        """Load and split the articles, embed the chunks (one call to Gemini) and store them, and make the retriever."""
        self.documents = load_documents(self.data_path)
        self.chunks = split_documents(self.documents, self.chunk_size, self.chunk_overlap)
        vectors = embed_chunks(self.chunks, self.embeddings)      # one call to Gemini: every chunk's embedding
        store = make_vector_store(self.embeddings, self.embedding_size, self.client, self.collection)
        store_vectors(store, self.chunks, vectors)
        self.retriever = make_retriever(store, self.top_k)

    def query(self, question: str) -> dict:
        """Answer one question: {"answer": ..., "sources": [...]}."""
        # The retriever turns the question into a vector, from the same model as the chunks so the two can be
        # compared (one call to Gemini), then Qdrant gives back the top_k closest chunks, closest first
        # invoke() comes from LangChain's Runnable: the retriever embeds the question and searches, in one call
        found = self._built_retriever().invoke(question)
        # What Gemini gets: the prompt, filled in with the chunks found and the question
        # format_messages() comes from LangChain's ChatPromptTemplate: the prompt's messages, filled in
        messages = prompt.format_messages(context=format_docs(found), question=question)
        # | joins the chat model and the parser into one Runnable
        # StrOutputParser comes from langchain_core: it turns the model's reply into plain text
        answer = (self.model | StrOutputParser()).invoke(messages)     # Gemini answers from the chunks found (one call)
        return self._with_sources(found, answer)

    def _built_retriever(self) -> VectorStoreRetriever:
        if self.retriever is None:
            raise RuntimeError("The engine isn't built yet: call build() first.")
        return self.retriever

    @staticmethod
    def _with_sources(docs: list[Document], answer: str) -> dict:
        """The answer, and the first MAX_SOURCES different articles among the chunks found, each with a snippet."""
        sources, seen = [], set()
        for doc in docs:
            if doc.metadata["doc_id"] in seen:     # two chunks of one article give one source
                continue
            seen.add(doc.metadata["doc_id"])
            text = doc.page_content
            snippet = text[:SNIPPET_LENGTH] + ("..." if len(text) > SNIPPET_LENGTH else "")
            sources.append({key: doc.metadata[key] for key in ("title", "system", "category")} | {"snippet": snippet})
            if len(sources) == MAX_SOURCES:
                break
        return {"answer": answer, "sources": sources}

    def stats(self) -> dict:
        """What the engine holds and how it's set up."""
        return {"documents": len(self.documents), "chunks": len(self.chunks), "collection": self.collection,
                "chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap, "top_k": self.top_k,
                "embedding_model": self.embedding_model_name, "chat_model": self.chat_model_name}


# The tests pass an engine with stand-ins for Gemini
def main(questions: list[str] = QUESTIONS, engine: RAGEngine | None = None) -> None:
    """Run every step in order: the build in one line, then each answer in full."""
    engine = engine if engine is not None else RAGEngine()
    engine.build()
    stats = engine.stats()
    print(f"Step 1: Build the engine: {stats['documents']} articles, {stats['chunks']} chunks")
    print("Step 2: Answer")
    print()
    for question in questions:
        print_result(question, engine.query(question))


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip()
    main([question] if question else QUESTIONS)     # no question, or only spaces: the sample questions
