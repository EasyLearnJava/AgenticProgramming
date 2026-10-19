"""
Project 11: what each call costs. The same Gemini welcome as project 10, plus the numbers behind it: tokens counted
before the call, tokens in and out after it, how long it took, and what it would cost.

    ask("Asha", 10)  ->  {"answer": "Welcome, Asha! LangChain", "finish_reason": "MAX_TOKENS", "counted_tokens": 21,
                          "input_tokens": 21, "output_tokens": 10, "thinking_tokens": 0, "latency_ms": 610,
                          "cost_usd": 3.13e-05}
                          (made-up example: Gemini's words and numbers change from call to call;
                          3.13e-05 is how Python writes 0.0000313)

Run it on its own:   python hello.py           ->   one call for Raghu, and its numbers
                     python hello.py Asha 10   ->   for Asha, with at most 10 output tokens: watch it get cut off
main.py imports ask() from here and serves it at POST /api/hello.
"""
import sys
import time

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 200           # the default cap, and the most the server lets one call ask for

# US dollars per 1 million tokens for this model, on the paid tier (Standard).
# From https://ai.google.dev/gemini-api/docs/pricing, checked on 2026-10-17. Prices change: check before you rely
# on them. Output tokens include the model's thinking tokens. On the free tier these calls cost nothing.
PRICE_PER_MILLION_INPUT = 0.30
PRICE_PER_MILLION_OUTPUT = 2.50

try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

# The same prompt and model as project 10.
prompt = PromptTemplate.from_template(
    "Write a short, friendly welcome for {name}, who is starting to learn LangChain. One or two sentences."
)
model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)


# The chain for one call: the prompt, then the model with this call's cap. No StrOutputParser this time: we want the
# whole AIMessage, because the token counts are in it.
# bind() wraps the model: every call made through the wrapper carries max_output_tokens, and `model` itself keeps its
# cap of 200. Bind the model, not the chain: (prompt | model).bind(...) hands the setting to the chain's first step,
# the prompt, which ignores it, so the cap is lost without any error.
def chain_for(max_output_tokens: int):
    return prompt | model.bind(max_output_tokens=max_output_tokens)


# The price of one call: tokens times the price per token. Input and output have different prices; output costs more.
def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_PER_MILLION_INPUT + output_tokens * PRICE_PER_MILLION_OUTPUT) / 1_000_000


# A cost as text. Python writes a float this small in its own way (7.379999999999999e-05), so show 7 decimal places,
# as the page does: "$0.0000738".
def dollars(usd: float) -> str:
    return f"${usd:.7f}"


# Everything worth showing about one call, read out of the model's reply (an AIMessage).
def usage_report(message: AIMessage, counted_tokens: int, latency_ms: int) -> dict:
    usage = message.usage_metadata                                  # filled in by Gemini, for every call
    return {
        # .text, not .content: this model's content is a list of blocks, and .text joins their text
        # (project 10's StrOutputParser did that for us).
        "answer": message.text,
        "finish_reason": message.response_metadata.get("finish_reason"),   # "STOP" = done, "MAX_TOKENS" = cut off
        "counted_tokens": counted_tokens,                           # counted before the call
        "input_tokens": usage["input_tokens"],                      # what Gemini says it read
        "output_tokens": usage["output_tokens"],                    # what it wrote, thinking included
        # output_token_details is there only when the model spent tokens thinking, so 0 when it's missing.
        "thinking_tokens": usage.get("output_token_details", {}).get("reasoning", 0),
        "latency_ms": latency_ms,
        "cost_usd": estimate_cost(usage["input_tokens"], usage["output_tokens"]),
    }


def ask(name: str, max_output_tokens: int = MAX_OUTPUT_TOKENS) -> dict:
    """One call, measured: count the prompt, call Gemini with this call's cap, time it, and read the numbers."""
    # ① Before: count the prompt's tokens. This is its own small request to Google (count_tokens), and it's free.
    counted_tokens = model.get_num_tokens(prompt.format(name=name))

    # ② The call itself, timed. perf_counter() is a stopwatch: only the difference between two readings matters.
    start = time.perf_counter()
    message = chain_for(max_output_tokens).invoke({"name": name})
    latency_ms = round((time.perf_counter() - start) * 1000)

    # ③ After: read the tokens, the finish reason and the cost out of the reply.
    return usage_report(message, counted_tokens, latency_ms)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else MAX_OUTPUT_TOKENS
    report = ask(name, limit)
    print(report["answer"])
    print()
    for key, value in report.items():
        if key == "answer":
            continue                                 # already printed above
        if key == "cost_usd":
            value = dollars(value)                   # "$0.0000738", not 7.379999999999999e-05
        print(f"{key:>16}: {value}")
