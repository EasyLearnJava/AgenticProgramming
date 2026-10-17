"""
Project 15: structured output. Gemini returns typed data instead of free text: a Pydantic object with every field
filled in and checked, ready for code to use.

    greet("Asha", "Hindi")                 ->  Greeting(message="नमस्ते आशा! ...", language="Hindi", emoji="🙏", tone="warm")
    triage("I was charged twice!!! ...")   ->  Ticket(intent="Refund a double charge", category="billing",
                                                      urgency="high", route_to_team="billing_team")
                                               (made-up examples: Gemini's words change every time)

Run it on its own:   python hello.py   ->   one greeting and one ticket, field by field
main.py imports the two chains from here and serves them at POST /api/greet and POST /api/triage.
"""
import sys
from typing import Literal, get_args

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from config import MissingKeyError, load_api_key

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 300

Language = Literal["English", "Hindi", "Telugu", "Tamil", "Spanish", "French"]
LANGUAGES = list(get_args(Language))          # ["English", "Hindi", ...]: the same list, for the page's dropdown


# ① The shapes we want back. Each field has a type, and a description that Gemini reads as an instruction.
#    Literal["warm", "playful", "formal"] means: one of these three, and nothing else.
class Greeting(BaseModel):
    """A short welcome for someone starting to learn LangChain."""
    message: str = Field(description="The welcome itself, one or two sentences, written in the requested language")
    language: Language = Field(description="The language the message is written in")
    emoji: str = Field(description="One emoji that fits the message")
    tone: Literal["warm", "playful", "formal"] = Field(description="How the message sounds")


class Ticket(BaseModel):
    """A customer support message, sorted so the right team can act on it."""
    intent: str = Field(description="What the customer wants, in at most ten words")
    category: Literal["billing", "technical", "account", "shipping", "other"]
    urgency: Literal["low", "medium", "high"] = Field(
        description="high: money lost, or the customer can't use the product at all; "
                    "medium: something is broken or late; low: a question or a request"
    )
    route_to_team: Literal["billing_team", "support_engineers", "account_team", "logistics", "general_support"]


try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)

# ② The prompts: ordinary chat prompts. They don't describe the format: the schema does that.
greet_prompt = ChatPromptTemplate.from_messages([
    ("system", "You write short, friendly welcomes for people who are starting to learn LangChain."),
    ("human", "Write a welcome for {name}, in {language}."),
])
triage_prompt = ChatPromptTemplate.from_messages([
    ("system", "You sort customer support messages for an online shop, so the right team can act on them."),
    ("human", "{message}"),
])

# ③ The chains. with_structured_output(Greeting) tells Gemini to answer in JSON that matches Greeting's schema,
#    then turns that JSON into a Greeting object. No StrOutputParser: what comes out is the object itself.
greet_chain = greet_prompt | model.with_structured_output(Greeting)
triage_chain = triage_prompt | model.with_structured_output(Ticket)

SAMPLE_MESSAGE = (
    "hi, i ordered the blue jacket last week and you took the money TWICE from my card!!! "
    "order 4471. i need it back before my rent is due on friday. also the jacket hasnt arrived yet"
)


if __name__ == "__main__":
    greeting = greet_chain.invoke({"name": "Asha", "language": "Hindi"})
    print("Greeting:", type(greeting).__name__)
    for field, value in greeting.model_dump().items():
        print(f"  {field:>13}: {value}")

    ticket = triage_chain.invoke({"message": SAMPLE_MESSAGE})
    print("\nTicket:", type(ticket).__name__)
    for field, value in ticket.model_dump().items():
        print(f"  {field:>13}: {value}")

    # Code can act on the fields straight away: no searching through text.
    if ticket.urgency == "high":
        print(f"\n-> {ticket.route_to_team} gets this first: {ticket.intent}")
