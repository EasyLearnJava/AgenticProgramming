"""
Project 12: streaming. The same kind of chain as project 10, but the answer arrives in pieces as Gemini writes it,
instead of all at once at the end.

    chain.invoke(...)   ->  waits, then gives the whole answer
    chain.stream(...)   ->  gives the answer piece by piece ("chunks"), each as soon as it is ready

Run it on its own:   python hello.py         ->   a welcome for Raghu, printed piece by piece, then the timings
                     python hello.py Asha    ->   one for Asha
main.py imports `chain` from here and streams it to the page with chain.astream(), the async twin of stream().
"""
import sys
import time

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 400           # a longer answer than before, so you can see it arrive

try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

# A longer answer than project 10's one or two sentences: with only a few words, streaming is over before you see it.
prompt = PromptTemplate.from_template(
    "Write a friendly welcome for {name}, who is starting to learn LangChain, in three short paragraphs: "
    "what LangChain is, what they will build first, and a word of encouragement."
)
model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)

# The same chain as project 10. Every Runnable can stream; StrOutputParser passes each piece of text on as it comes.
chain = prompt | model | StrOutputParser()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    start = time.perf_counter()
    first_ms = None
    pieces = 0
    for chunk in chain.stream({"name": name}):           # a for loop: each turn gets the next piece
        if first_ms is None:
            first_ms = round((time.perf_counter() - start) * 1000)
        pieces += 1
        print(chunk, end="", flush=True)                 # flush: show it now, don't wait for the end of the line
    total_ms = round((time.perf_counter() - start) * 1000)
    print(f"\n\nfirst words after {first_ms} ms, all of it after {total_ms} ms, in {pieces} pieces")
