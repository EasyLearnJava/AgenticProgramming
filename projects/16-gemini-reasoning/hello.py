"""
Project 16: reasoning. The same multi-step questions asked three ways, to see what reasoning first buys you, and
what it costs:

    direct        "reply with only the answer"
    step_by_step  "work through it step by step, then give the answer" (chain-of-thought, in the prompt)
    thinking      "reply with only the answer", but with Gemini's thinking turned up (thinking_level="high")

Every way ends with a line "Answer: <number>", so code can check it against the right answer. Then a second part:
one prompt full of common mistakes (anti-patterns), and the same prompt fixed.

Run it on its own:   python hello.py   ->   the table for the three ways, then the prompt before and after
main.py imports from here and serves it at POST /api/compare and POST /api/fix.
"""
import asyncio
import re
import sys
import time

from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 2000          # room for the steps: thinking tokens count towards this cap too
AT_ONCE = 4                       # at most 4 calls running at the same time (the free tier limits calls per minute)

# ① Questions with one right number each. Several are classic traps: the quick answer that comes to mind is wrong.
QUESTIONS = [
    {"question": "A bat and a ball cost 110 rupees in total. The bat costs 100 rupees more than the ball. "
                 "How many rupees does the ball cost?", "answer": 5},
    {"question": "Asha has 3 boxes with 12 apples in each. She gives away a third of all her apples, "
                 "then buys 7 more. How many apples does she have now?", "answer": 31},
    {"question": "If 5 machines take 5 minutes to make 5 widgets, how many minutes do 100 machines take "
                 "to make 100 widgets?", "answer": 5},
    {"question": "A patch of lily pads doubles in size every day. It takes 48 days to cover the whole lake. "
                 "How many days does it take to cover half of the lake?", "answer": 47},
    {"question": "A shirt costs 800 rupees. Its price is cut by 25%, and then the new price goes up by 10%. "
                 "What is the final price in rupees?", "answer": 660},
    {"question": "Ravi reads 15 pages on Monday. Each day after that he reads 5 more pages than the day before. "
                 "How many pages has he read in total by the end of Friday?", "answer": 125},
]

ANSWER_LINE = 'End with one line in the form "Answer: <number>", with only the number on it.'

# ② The three ways. Only the system prompt and the thinking level change; the question is the same.
WAYS = {
    "direct": {
        "system": f"You solve maths word problems. Reply with only the answer. {ANSWER_LINE}",
        "thinking_level": None,                      # the model's default: "minimal" for this model
    },
    "step_by_step": {
        "system": f"You solve maths word problems. Work through the problem step by step, "
                  f"writing each step on its own line, then check your result. {ANSWER_LINE}",
        "thinking_level": None,
    },
    "thinking": {
        "system": f"You solve maths word problems. Reply with only the answer. {ANSWER_LINE}",
        "thinking_level": "high",                    # the model reasons privately before it writes the answer
    },
}

try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)


# ③ One chain per way. bind(thinking_level=...) changes the setting for that chain only.
def make_chain(way: dict):
    prompt = ChatPromptTemplate.from_messages([("system", way["system"]), ("human", "{question}")])
    step = model.bind(thinking_level=way["thinking_level"]) if way["thinking_level"] else model
    return prompt | step                     # no parser: the token counts are in the AIMessage


chains = {name: make_chain(way) for name, way in WAYS.items()}


# ④ Reading and checking the answer: plain code, no model.
def read_answer(text: str) -> float | None:
    """The number on the last "Answer:" line, or None if there isn't one. "Answer: 1,250" -> 1250.0"""
    found = re.findall(r"Answer:\s*[₹$]?\s*(-?[\d,]*\.?\d+)", text)
    return float(found[-1].replace(",", "")) if found else None


def report(message: AIMessage, expected: float, latency_ms: int) -> dict:
    value = read_answer(message.text)
    usage = message.usage_metadata or {}
    return {
        "text": message.text,
        "value": value,
        "correct": value == expected,
        "output_tokens": usage.get("output_tokens", 0),            # the visible answer plus any thinking
        "thinking_tokens": usage.get("output_token_details", {}).get("reasoning", 0),
        "latency_ms": latency_ms,
    }


async def ask(way: str, item: dict, limit: asyncio.Semaphore) -> dict:
    """One question, one way, timed. Any failure comes back as an error for that one cell."""
    async with limit:                        # wait here if AT_ONCE calls are already running
        try:
            start = time.perf_counter()
            message = await chains[way].ainvoke({"question": item["question"]})
            return report(message, item["answer"], round((time.perf_counter() - start) * 1000))
        except Exception as err:
            return {"error": f"Gemini didn't answer ({type(err).__name__}).", "detail": str(err)}


async def compare() -> list[dict]:
    """Every question, every way: 6 x 3 = 18 calls, at most AT_ONCE at a time."""
    limit = asyncio.Semaphore(AT_ONCE)
    # Start all 18 at once; the semaphore lets only AT_ONCE through at a time. gather keeps them in order.
    results = await asyncio.gather(*(ask(way, item, limit) for item in QUESTIONS for way in WAYS))
    rows = []
    for i, item in enumerate(QUESTIONS):
        cells = results[i * len(WAYS):(i + 1) * len(WAYS)]
        rows.append({"question": item["question"], "expected": item["answer"], "ways": dict(zip(WAYS, cells))})
    return rows


def summary(rows: list[dict]) -> dict:
    """Per way: how many were right, and the average tokens and time of the calls that answered."""
    result = {}
    for way in WAYS:
        cells = [row["ways"][way] for row in rows if "error" not in row["ways"][way]]
        count = len(cells) or 1
        result[way] = {
            "correct": sum(cell["correct"] for cell in cells),
            "answered": len(cells),
            "avg_output_tokens": round(sum(cell["output_tokens"] for cell in cells) / count),
            "avg_thinking_tokens": round(sum(cell["thinking_tokens"] for cell in cells) / count),
            "avg_latency_ms": round(sum(cell["latency_ms"] for cell in cells) / count),
        }
    return result


# ⑤ Part two: one prompt with four common mistakes, and the same request fixed.
BEFORE_PROMPT = (
    "Look at this message from a customer and tell me about it. Keep it short but explain everything in detail, "
    "and write them a reply too.\n\n{message}"
)
AFTER_SYSTEM = "You read customer support messages for an online shop."
AFTER_PROMPT = (
    'Say what the customer wants, in one sentence of at most 20 words, starting with "The customer wants". '
    "Do not write a reply.\n\n"
    "Customer message:\n{message}"
)
ANTI_PATTERNS = [
    {"mistake": "A vague goal", "before": '"tell me about it"', "after": '"say what the customer wants"'},
    {"mistake": "Instructions that conflict", "before": '"keep it short but explain everything in detail"',
     "after": '"one sentence of at most 20 words"'},
    {"mistake": "No output format", "before": "(none: any shape will do)", "after": '"starting with \'The customer wants\'"'},
    {"mistake": "Several tasks in one request", "before": '"tell me about it ... and write them a reply too"',
     "after": 'one task, and "Do not write a reply"'},
]
SAMPLE_MESSAGE = (
    "hi, i ordered the blue jacket last week and you took the money TWICE from my card!!! "
    "order 4471. i need it back before my rent is due on friday. also the jacket hasnt arrived yet"
)

before_chain = ChatPromptTemplate.from_messages([("human", BEFORE_PROMPT)]) | model | StrOutputParser()
after_chain = (ChatPromptTemplate.from_messages([("system", AFTER_SYSTEM), ("human", AFTER_PROMPT)])
               | model | StrOutputParser())


if __name__ == "__main__":
    rows = asyncio.run(compare())
    for row in rows:
        print(f"=== {row['question']}  (right answer: {row['expected']})")
        for way, cell in row["ways"].items():
            if "error" in cell:
                print(f"  {way:>12}: {cell['error']}")
            else:
                mark = "right" if cell["correct"] else "WRONG"
                print(f"  {way:>12}: {cell['value']} {mark}  {cell['output_tokens']} tokens "
                      f"({cell['thinking_tokens']} thinking), {cell['latency_ms']} ms")
    print()
    for way, s in summary(rows).items():
        print(f"{way:>12}: {s['correct']} of {s['answered']} right, on average {s['avg_output_tokens']} output "
              f"tokens ({s['avg_thinking_tokens']} thinking) and {s['avg_latency_ms']} ms")

    print("\n=== The prompt before\n" + before_chain.invoke({"message": SAMPLE_MESSAGE}))
    print("\n=== The prompt after\n" + after_chain.invoke({"message": SAMPLE_MESSAGE}))
