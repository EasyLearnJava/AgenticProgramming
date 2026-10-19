"""
The Gemini models, with the key checked first: the embedding model, which turns a text into a vector (a list of
numbers whose direction stands for its meaning), and the chat model, which writes the answers.

    embeddings.embed_documents(["Title: VPN ...", ...])  ->  768 numbers per text   (one call to Gemini for the list)
    embeddings.embed_query("My VPN won't connect")       ->  768 numbers            (one call to Gemini)
    chat_model.invoke("...")                             ->  an AIMessage with Gemini's reply   (one call)

Building a model makes no call: each embed_... and each invoke does, and uses your key's quota. Every module that
needs Gemini imports it from here.
"""
import sys

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from config import MissingKeyError, load_api_key

# ① The models' names and settings: the one place the code names them (a test checks them).
#    gemini-embedding-001 is Gemini's text embedding model. It can give 128 to 3072 numbers per text; 768 is one of
#    the sizes Google recommends, and smaller vectors are cheaper to store and to compare.
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_SIZE = 768
CHAT_MODEL = "gemini-3.5-flash-lite"    # small, fast and cheap, as in the tutorials
MAX_OUTPUT_TOKENS = 500                 # a cap on each answer's length, and so on its cost

# ② The key, checked first, as in the tutorials. No key, no models.
try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the models: {err}")

# ③ The embedding model. embed_documents() tells Gemini the texts are documents to be found (RETRIEVAL_DOCUMENT), and
#    embed_query() that the text is a question looking for them (RETRIEVAL_QUERY). Gemini embeds the two kinds a
#    little differently, so that a question lands near the documents that answer it.
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=api_key,
                                          output_dimensionality=EMBEDDING_SIZE)


# ④ The chat model. No temperature is set: gemini-3.5-flash-lite uses fixed sampling settings, and LangChain drops a
#    temperature given to it, with a warning. What keeps its answers close to the articles is the prompt (step 07).
chat_model = ChatGoogleGenerativeAI(model=CHAT_MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)
