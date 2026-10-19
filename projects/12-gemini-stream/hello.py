"""
Project 12: streaming. The same shape of chain as project 10, but the answer arrives in pieces as Gemini writes it,
instead of all at once at the end.

    chain.invoke({"name": "Asha"})  ->  waits, then gives the whole answer as one string
    chain.stream({"name": "Asha"})  ->  "Welcome, Asha!", " LangChain is a", " framework for", ...
                                        the answer in pieces ("chunks"), each one as soon as it's ready
                                        (made-up pieces: Gemini's words, and where it cuts them, change every time)

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
MAX_OUTPUT_TOKENS = 400           # project 10 had 200: room for a longer answer, so you can watch it arrive

# ① The key, checked first (project 9). No key, no chain.
try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

# ② The prompt asks for more than project 10's one or two sentences: with only a few words, streaming is over before
#    you see it.
prompt = PromptTemplate.from_template(
    "Write a friendly welcome for {name}, who is starting to learn LangChain, in three short paragraphs: "
    "what LangChain is, what they will build first, and a word of encouragement."
)

# ③ The model: the same as project 10, with room for a longer answer.
model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)

# ④ The chain: the same shape as project 10's. Every chain has stream() as well as invoke(), and here the pieces get
#    through one by one because StrOutputParser passes each piece's text on as it comes. (A plain function step after
#    it, a RunnableLambda, would wait for the whole answer and pass it on in one piece.)
chain = prompt | model | StrOutputParser()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"

    # ⑤ Stream it: print each piece the moment it arrives, and time the first piece and the end.
    start = time.perf_counter()
    first_ms = None
    piece_count = 0
    for piece in chain.stream({"name": name}):           # a for loop: each turn waits for the next piece
        if first_ms is None:
            first_ms = round((time.perf_counter() - start) * 1000)   # the time to the first words
        piece_count += 1
        print(piece, end="", flush=True)                 # flush: show it now, don't wait for the end of the line
    total_ms = round((time.perf_counter() - start) * 1000)
    print(f"\n\nfirst words after {first_ms} ms, all of it after {total_ms} ms, in {piece_count} pieces")
