"""
IT Knowledge Base: The Embedding Model
======================================

Builds Gemini's embedding model, which turns a text into a vector: a list of numbers that stands for its meaning.
It handles:
  1. Naming the model and the vector size in one place
  2. Checking the API key first: no key, no model

    embeddings.embed_documents(["Title: VPN ...", ...])  ->  768 numbers per text   (one call for the list)
    embeddings.embed_query("My VPN won't connect")       ->  768 numbers            (one call)

Building the model makes no call to Gemini: each embed_... does, and uses your key's quota.
"""
import sys

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import MissingKeyError, load_api_key

# gemini-embedding-001 gives 128 to 3072 numbers per text; 768 is a size Google recommends, and cheaper to store
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768

try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the models: {err}")

# embed_documents() embeds texts as documents to be found, embed_query() as a question looking for them
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key,
                                          output_dimensionality=EMBEDDING_SIZE)
