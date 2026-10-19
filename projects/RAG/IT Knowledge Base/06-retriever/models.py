"""
The Gemini model this step uses, with the key checked first: the embedding model, which turns a text into a vector,
a list of numbers. Texts with close meanings get vectors that point in close directions.

    embeddings.embed_documents(["Title: VPN ...", ...])  ->  768 numbers per text   (one call to Gemini for the list)
    embeddings.embed_query("My VPN won't connect")       ->  768 numbers            (one call to Gemini)

Building the model makes no call: each embed_... does, and uses your key's quota. Every module that needs Gemini
imports it from here.
"""
import sys

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import MissingKeyError, load_api_key

# ① The model's name and the vector size: the one place the code names them (a test checks them).
#    gemini-embedding-001 is Gemini's text embedding model. It can give 128 to 3072 numbers per text; 768 is one of
#    the sizes Google recommends, and smaller vectors are cheaper to store and to compare.
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768

# ② The key, checked first, as in the tutorials. No key, no model.
try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the models: {err}")

# ③ The embedding model. embed_documents() tells Gemini the texts are documents to be found (RETRIEVAL_DOCUMENT), and
#    embed_query() that the text is a question looking for them (RETRIEVAL_QUERY). Gemini embeds the two kinds a
#    little differently, so that a question lands near the documents that answer it.
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key,
                                          output_dimensionality=EMBEDDING_SIZE)
