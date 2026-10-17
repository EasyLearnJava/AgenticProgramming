"""
Project 13: the system prompt. One question, answered twice: once for a beginner and once for an expert. The only
difference between the two is the system message, the instructions that set the model's role, audience, tone and
length. The user's question goes in a separate human message.

    {"question": "What is an API?"}  ->  {"beginner": "An API is like a waiter ...",
                                          "expert": "An API is a contract ... versioning ..."}

Run it on its own:   python hello.py                         ->   "What is an API?" for both audiences
                     python hello.py "What is a database?"   ->   your own question
main.py imports `chain` from here and serves it at POST /api/ask.
"""
import sys

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 300

# ① The two system prompts: the rules for each audience. Each one says who the model is, who it's talking to, how
#    to sound, and how long to be. Change only these to change the style.
SYSTEM_PROMPTS = {
    "beginner": (
        "You are a patient teacher. The person asking has never written code. "
        "Explain in plain, everyday words and use one comparison from daily life. "
        "Use no technical terms and no code. Answer in at most three short sentences."
    ),
    "expert": (
        "You are a senior software engineer talking to another experienced developer. "
        "Be precise and use the correct technical terms. Mention one trade-off or pitfall. "
        "No greetings and no analogies. Answer in at most three sentences."
    ),
}

try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)


# ② One prompt per audience: a list of messages instead of one string. The system message holds the rules; the
#    human message holds the user's words. {question} is filled in only in the human message, so whatever the user
#    types lands there, and never inside the rules.
def make_prompt(system_prompt: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}"),
    ])


prompts = {audience: make_prompt(text) for audience, text in SYSTEM_PROMPTS.items()}

# ③ Both audiences at once: RunnableParallel (project 6) gives the same input to each chain, and the two Gemini
#    calls run at the same time.
chain = RunnableParallel({audience: prompt | model | StrOutputParser() for audience, prompt in prompts.items()})


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "What is an API?"
    answers = chain.invoke({"question": question})
    for audience, answer in answers.items():
        print(f"--- for a {audience} ---")
        print(answer)
        print()
