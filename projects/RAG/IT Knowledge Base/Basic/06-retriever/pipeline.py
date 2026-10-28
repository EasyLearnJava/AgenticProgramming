"""
IT Knowledge Base: The Retriever
================================

The project's code in one file: it reads the IT knowledge base CSV file into LangChain Documents, cuts them into
chunks, embeds every chunk with Gemini, stores the chunks in Qdrant, in memory, then finds the chunks closest to a
question: the question is embedded with the same model as the chunks, and Qdrant gives back the closest ones. It
handles:
  1. Reading each article into a Document: its text in page_content, its labels in metadata
  2. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  3. Building Gemini's embedding model, after config.py has checked the API key: no key, no model
  4. Embedding every chunk's text in one call to Gemini
  5. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  6. Making the LangChain store on it, which keeps the embedding model for searches
  7. Storing the chunks with the vectors embed_chunks() made for them: no call to Gemini there
  8. Making a retriever that embeds and searches in one call, and returns TOP_K chunks
  9. Turning the chunks into one numbered, titled text for a prompt
  10. Running the steps: main() names them, runs them, then prints the search with utils.py's print_retrieval()

Building the model makes no call to Gemini: each embed_... does, and uses your key's quota.

Usage:
    python pipeline.py                      # each step for "How do I fix VPN connection timeouts?"
    python pipeline.py "my email bounced"   # each step for your question (3 calls to Gemini)
"""
import csv
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import MissingKeyError, load_api_key
from utils import print_retrieval

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

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"

TOP_K = 5      # how many chunks each search returns
QUESTIONS = [  # the course app's sample questions
    "How do I fix VPN connection timeouts?",
    "I can't set up MFA on my mobile device",
    "My laptop is running very slow",
]


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


try:
    api_key = load_api_key()
except MissingKeyError as err:
    # exit() comes from Python's sys module: it stops the program with this message
    sys.exit(f"Can't build the models: {err}")

# embed_documents() embeds texts as documents to be found, embed_query() as a question looking for them
# GoogleGenerativeAIEmbeddings comes from langchain_google_genai: LangChain's class for Gemini's embeddings
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key,
                                          output_dimensionality=EMBEDDING_SIZE)


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

    # Other ways to search, off for now: to try one, comment out the return above and uncomment one below.
    # None of them checks that a chunk answers the question: each only changes which close chunks come back.
    #
    # 1. A minimum score: drops chunks that aren't close enough, so a question the articles don't cover gets fewer
    #    than k chunks, or none. score_threshold isn't the cosine pipeline.py prints: LangChain turns the cosine
    #    into (cosine + 1) / 2, so 0.8 keeps chunks with a cosine of 0.6 or more.
    # return store.as_retriever(search_type="similarity_score_threshold",
    #                           search_kwargs={"k": k, "score_threshold": 0.8})
    #
    # 2. MMR (maximal marginal relevance): takes the 20 closest chunks, then picks k that are close to the question
    #    and different from each other, so near-copies don't fill every place. lambda_mult=1 is closeness only.
    # return store.as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": 20, "lambda_mult": 0.5})
    #
    # 3. A filter: searches only the chunks with one label, here the "Remote Access" category. It needs
    #    `from qdrant_client import models`; each point keeps its labels under "metadata".
    # return store.as_retriever(search_kwargs={"k": k, "filter": models.Filter(must=[models.FieldCondition(
    #     key="metadata.category", match=models.MatchValue(value="Remote Access"))])})


def format_docs(docs: list[Document]) -> str:
    """The chunks as one text for a prompt, each numbered and titled so an answer can name its article."""
    return "\n\n".join(f"[{number}] {doc.metadata['title']}\n{doc.page_content}" for number, doc in enumerate(docs, 1))


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(question: str = QUESTIONS[0], embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE) -> None:
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
    print("Step 5: Retrieve")
    # The question becomes a vector from the same model as the chunks, so the two can be compared (one call)
    # embed_query() comes from LangChain's Embeddings (Gemini's, here): one text in, one vector out
    question_vector = embeddings.embed_query(question)
    # similarity_search_with_score_by_vector() comes from langchain_qdrant's QdrantVectorStore: k closest, scored
    scored = store.similarity_search_with_score_by_vector(question_vector, k=TOP_K)
    # The retriever does both in one call (one more call to Gemini), without the scores
    # invoke() comes from LangChain's Runnable: the retriever embeds the question and searches, in one call
    found = make_retriever(store).invoke(question)
    # The top chunk's vector, read back from Qdrant by its point's id, so its score can be worked out by hand
    # langchain_qdrant puts each found point's id in the chunk's metadata, under "_id"
    # retrieve() comes from qdrant_client's QdrantClient: points by id, with their vectors when asked
    top_point = store.client.retrieve(store.collection_name, [scored[0][0].metadata["_id"]], with_vectors=True)[0]
    # A sample of what a prompt gets: the first 2 chunks, as one text
    print_retrieval(question, question_vector, scored, found, top_point.vector, format_docs(found[:2]))


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or QUESTIONS[0])
