"""
Project 10: the first real LLM call. The same {name} input as project 4, but now Gemini writes the greeting.

    prompt | model | parser
    PromptTemplate     ->  ChatGoogleGenerativeAI  ->  StrOutputParser
    fills in {name}        Gemini writes a reply       the reply message -> plain text

Run it on its own:   python hello.py         ->   a welcome for Raghu, written by Gemini
                     python hello.py Asha    ->   one for Asha
Each run is a real call: the words change from run to run, and it uses your key's quota.
main.py imports `chain` from here and serves it at POST /api/hello.
"""
import sys

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"   # small, fast and cheap: the one place the code names the model (a test checks it)
MAX_OUTPUT_TOKENS = 200           # a cap on the length of each answer, and so on its cost

# ① The key, checked first (project 9). No key, no chain.
try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

# ② The prompt: the same kind of template as before. The text it makes is now an instruction for the model.
prompt = PromptTemplate.from_template(
    "Write a short, friendly welcome for {name}, who is starting to learn LangChain. One or two sentences."
)

# ③ The model. Building it makes no call: the call happens each time the chain runs.
#    The key goes in here and only here. The model keeps it as a SecretStr, which prints as '**********'.
#    It takes the prompt's output as it is: a chat model turns the StringPromptValue into one HumanMessage
#    (a chat message from the user), so no to_text step is needed between them.
model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)

# ④ The parser: the model gives back an AIMessage (text plus details); this keeps just the text.
#    It takes the place of the to_text step from projects 2 to 7.
parser = StrOutputParser()

# ⑤ The chain, built with | as before.
chain = prompt | model | parser


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    print(chain.invoke({"name": name}))
