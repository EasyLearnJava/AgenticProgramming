"""
Project 14: few-shot examples. Show the model two or three example answers, and it copies their format instead of
guessing. The same questions are asked twice: without examples and with them. follows_format() checks each answer,
so you can count how many kept the format.

The format the examples show (the system prompt never describes it):

    In one line: <a one-sentence explanation>
    Example: <a tiny example>
    Watch out: <one common mistake>

Run it on its own:   python hello.py   ->   the 10 questions, without and with examples, and how many kept the format
main.py imports `chain` and `follows_format` from here and serves them at POST /api/compare.
"""
import sys

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_core.runnables import RunnableParallel
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 200

# The same short system prompt for both. It says what to do, but nothing about the format: only the examples show it.
SYSTEM_PROMPT = "You answer programming questions for beginners."

# ① The examples: three questions, each with an answer in exactly the format we want. They agree with each other:
#    the same three labels, in the same order, one line each, about the same length.
EXAMPLES = [
    {
        "question": "What is a variable?",
        "answer": "In one line: A variable is a name that holds a value, so you can use it later.\n"
                  "Example: age = 30 stores 30 under the name age.\n"
                  "Watch out: In Python, = stores a value and == compares two values.",
    },
    {
        "question": "What is a loop?",
        "answer": "In one line: A loop runs the same lines again, once for each item or until a condition is false.\n"
                  "Example: for name in [\"Asha\", \"Ravi\"]: print(name) prints each name.\n"
                  "Watch out: A while loop whose condition never becomes false runs forever.",
    },
    {
        "question": "What is a function?",
        "answer": "In one line: A function is a named block of code you can run whenever you need it.\n"
                  "Example: def greet(name): return \"Hi \" + name, then greet(\"Asha\") gives \"Hi Asha\".\n"
                  "Watch out: Defining a function doesn't run it; calling it does.",
    },
]

# Ten questions to compare on. None of them is one of the examples.
QUESTIONS = [
    "What is a list?",
    "What is an if statement?",
    "What is a string?",
    "What is a dictionary?",
    "What is a class?",
    "What is an API?",
    "What is a bug?",
    "What is a comment?",
    "What is an exception?",
    "What is a module?",
]

LABELS = ("In one line:", "Example:", "Watch out:")


# ② The check: exactly three lines, starting with the three labels in order. Plain code, no model.
def follows_format(answer: str) -> bool:
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    return len(lines) == len(LABELS) and all(line.startswith(label) for line, label in zip(lines, LABELS))


try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)

# ③ How one example becomes messages: the question as a human message, the answer as an AI message, as if the model
#    had answered it that way before.
example_prompt = ChatPromptTemplate.from_messages([("human", "{question}"), ("ai", "{answer}")])
few_shot = FewShotChatMessagePromptTemplate(examples=EXAMPLES, example_prompt=example_prompt)

# ④ The two prompts. The only difference is the examples, placed between the system message and the real question.
without_examples = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{question}")])
with_examples = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), few_shot, ("human", "{question}")])

# ⑤ Both for each question, side by side (project 6).
chain = RunnableParallel({
    "without": without_examples | model | StrOutputParser(),
    "with": with_examples | model | StrOutputParser(),
})


if __name__ == "__main__":
    # batch() (project 7): all ten questions, at most 2 at a time, so 4 calls at most are running at once.
    results = chain.batch([{"question": q} for q in QUESTIONS], config={"max_concurrency": 2})
    for question, answers in zip(QUESTIONS, results):
        print(f"=== {question}")
        for kind in ("without", "with"):
            mark = "follows the format" if follows_format(answers[kind]) else "does NOT follow the format"
            print(f"--- {kind} examples: {mark}")
            print(answers[kind].strip())
        print()
    for kind in ("without", "with"):
        kept = sum(follows_format(answers[kind]) for answers in results)
        print(f"{kind} examples: {kept} of {len(QUESTIONS)} answers follow the format")
