"""
Load the IT knowledge base into a vector store: read, chunk, embed, save.

Usage:
    python ingest.py
"""
import csv
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "data" / "sample_it_kb.csv"
STORE_DIR = HERE / "qdrant_data"   # the vectors are saved here, on disk
COLLECTION = "it_kb"

load_dotenv(HERE / ".env")   # puts GOOGLE_API_KEY from .env in the environment

# 1. Read: one Document per article (one CSV row), as "column: value" lines
docs = []
with open(DATA_FILE, encoding="utf-8", newline="") as file:
    for row in csv.DictReader(file):
        text = "\n".join(f"{column}: {value}" for column, value in row.items())
        docs.append(Document(page_content=text, metadata={"title": row["title"]}))
print(f"Read {len(docs)} articles")

# 2. Chunk: cut each article into pieces of up to 500 characters, 50 shared between neighbours
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)
print(f"Cut them into {len(chunks)} chunks")

# 3. Embed and save: Gemini turns each chunk into a vector, Qdrant saves them in qdrant_data/
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
QdrantVectorStore.from_documents(chunks, embeddings, path=str(STORE_DIR), collection_name=COLLECTION,
                                 force_recreate=True)   # start fresh on every run
print(f"Saved {len(chunks)} vectors in {STORE_DIR.name}/. Now run: python ask.py")
