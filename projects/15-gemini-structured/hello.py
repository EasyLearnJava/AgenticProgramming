"""
Project 15: structured output. Gemini returns typed data instead of free text: a Pydantic object with every field
filled in and checked, ready for code to use.

    greet_chain.invoke({"name": "Asha", "language": "Hindi"})
        ->  Greeting(message="नमस्ते आशा! ...", language="Hindi", emoji="🙏", tone="warm")
    triage_chain.invoke({"message": "hi, i ordered the blue jacket ... you took the money TWICE ..."})
        ->  Ticket(intent="Refund a double charge", category="billing", urgency="high", route_to_team="billing_team")
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
MAX_OUTPUT_TOKENS = 300           # an answer cut off at this cap is missing its last fields, and the parser refuses it

# The languages, listed once. Greeting uses them (what Gemini may answer), and so do main.py's GreetIn (what the page
# may send) and the page's dropdown.
Language = Literal["English", "Hindi", "Telugu", "Tamil", "Spanish", "French"]
LANGUAGES = list(get_args(Language))          # get_args() lists a Literal's choices: ["English", "Hindi", ...]


# ① The shapes we want back. Each field has a type, and can have a description that Gemini reads as an instruction.
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

# ③ The chains. model.with_structured_output(Greeting) adds two steps. First the model, with two settings bound to it
#    (bind(), as in project 11): answer in JSON, and fit Greeting's JSON schema. This is Gemini's native structured
#    output (method="json_schema", the default). Then a parser that turns the JSON into a Greeting object, and refuses
#    anything that doesn't fit. No StrOutputParser: what comes out is the object itself.
greet_chain = greet_prompt | model.with_structured_output(Greeting)
triage_chain = triage_prompt | model.with_structured_output(Ticket)

# A messy message to sort: lower case, typos, shouting, and two problems at once (a double charge, a late jacket).
SAMPLE_MESSAGE = (
    "hi, i ordered the blue jacket last week and you took the money TWICE from my card!!! "
    "order 4471. i need it back before my rent is due on friday. also the jacket hasnt arrived yet"
)


if __name__ == "__main__":
    greeting = greet_chain.invoke({"name": "Asha", "language": "Hindi"})
    print(f"greet_chain returned a {type(greeting).__name__} object, not a str:")
    for field, value in greeting.model_dump().items():     # model_dump(): the object's fields, as a dict
        print(f"  {field:>13}: {value}")                   # :>13 right-aligns each name, so the colons line up

    ticket = triage_chain.invoke({"message": SAMPLE_MESSAGE})
    print(f"\ntriage_chain returned a {type(ticket).__name__} object:")
    for field, value in ticket.model_dump().items():
        print(f"  {field:>13}: {value}")

    # Code can act on the fields straight away: no searching through text.
    if ticket.urgency == "high":
        print(f"\n-> {ticket.route_to_team} gets this first: {ticket.intent}")
