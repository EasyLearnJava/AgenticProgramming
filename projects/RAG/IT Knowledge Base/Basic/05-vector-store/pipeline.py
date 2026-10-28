"""
IT Knowledge Base: The Vector Store
===================================

The project's code in one file: it reads the IT knowledge base CSV file into LangChain Documents, cuts them into
chunks, embeds every chunk with Gemini, then stores the chunks in Qdrant, the vector database, running in memory
inside this process: one point per chunk, with its vector, its text and its metadata. It handles:
  1. Reading each article into a Document: its text in page_content, its labels in metadata
  2. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  3. Building Gemini's embedding model, after config.py has checked the API key: no key, no model
  4. Embedding every chunk's text in one call to Gemini
  5. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine, with the settings for an index
     (which Qdrant ignores in memory); any old one is deleted first
  6. Making the LangChain store on it, which keeps the embedding model for searches
  7. Storing the chunks with the vectors embed_chunks() made for them: no call to Gemini there
  8. Running the steps: main() names them, runs them, then prints the points with utils.py's print_points()

Building the model makes no call to Gemini: each embed_... does, and uses your key's quota.

Usage:
    python pipeline.py    # Qdrant runs in memory, inside this script: the points are gone when it ends
"""
import csv
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, HnswConfigDiff, PointStruct, VectorParams

from config import MissingKeyError, load_api_key
from utils import print_points

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
    # HnswConfigDiff comes from qdrant_client too: the settings for an index, HNSW, a graph linking each vector to its
    # m nearest, so a search hops through the graph and checks a small part of the vectors, not all of them.
    # ef_construct is how thoroughly it searches while building the graph; 16 and 100 are Qdrant's defaults.
    # An index makes search faster, not better: at best it finds the same chunks as comparing every vector.
    # Here it does nothing: in memory, Qdrant ignores these settings and compares every vector, which is fine for 28.
    # A Qdrant server (in Docker, say) builds the index only once it holds thousands of chunks, not 28
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                             hnsw_config=HnswConfigDiff(m=16, ef_construct=100))
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


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    vectors = embed_chunks(chunks, embeddings)     # one call to Gemini: every chunk's embedding
    print(f"Step 3: Embed: {len(vectors)} vectors of {len(vectors[0])} numbers")
    print("Step 4: Store")
    print("Qdrant: in memory, inside this script: the points are gone when it ends")
    store = make_vector_store(embeddings, size)    # Qdrant in memory, and a new collection in it
    store_vectors(store, chunks, vectors)          # Step 3's vectors: no call to Gemini
    print_points(store)


if __name__ == "__main__":
    main()
