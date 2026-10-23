"""
IT Knowledge Base: The Gemini Models
====================================

Builds the two Gemini models every other file imports from here. It handles:
  1. The embedding model, which turns a text into a vector: a list of numbers that stands for its meaning
  2. The chat model, which writes the answers
  3. Checking the API key first: no key, no models

    embeddings.embed_documents(["Title: VPN ...", ...])  ->  768 numbers per text   (one call for the list)
    embeddings.embed_query("My VPN won't connect")       ->  768 numbers            (one call)
    chat_model.invoke("...")                             ->  an AIMessage with Gemini's reply   (one call)

Building a model makes no call to Gemini: each embed_... and each invoke does, and uses your key's quota.
"""
import sys

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from config import MissingKeyError, load_api_key

# gemini-embedding-001 gives 128 to 3072 numbers per text; 768 is a size Google recommends, and cheaper to store
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768
CHAT_MODEL = "gemini-3.5-flash-lite"    # small, fast and cheap
MAX_OUTPUT_TOKENS = 500                 # a cap on each answer's length, and so on its cost

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
