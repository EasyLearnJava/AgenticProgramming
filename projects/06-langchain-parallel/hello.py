"""
Project 6: one input, several results at once. The greeting goes into a RunnableParallel, which runs three steps
side by side on it and returns a dict; then RunnablePassthrough.assign() adds one more key.

    prompt | to_text | RunnableParallel(original, upper, length) | RunnablePassthrough.assign(shout)

Run it on its own:   python hello.py         ->   the four results for "Raghu", then the chain's graph
                     python hello.py Asha    ->   the same for "Asha"
main.py imports `chain` from here and serves it at POST /api/hello, and its graph at GET /api/graph.
"""
import json
import sys

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

# ① The template, with one input: {name}. Same as project 4.
prompt = PromptTemplate.from_template("Hello {name}, welcome to LangChain!")

# ② The converter: the prompt gives back an object (a StringPromptValue), this turns it into text.
to_text = RunnableLambda(lambda value: value.to_string(), name="to_text")

# ③ Side by side: every step gets the SAME input (the greeting), and the results come back as one dict.
#    RunnablePassthrough() does nothing to its input: it passes it through, so the original stays in the result.
side_by_side = RunnableParallel(
    original=RunnablePassthrough(),       # "Hello Raghu, welcome to LangChain!"
    upper=RunnableLambda(str.upper),      # "HELLO RAGHU, WELCOME TO LANGCHAIN!"
    length=RunnableLambda(len),           # 34
)


# ④ .assign() takes the dict, keeps every key, and adds one computed from it.
def shout(result: dict) -> str:
    return result["upper"].replace("!", "!!!")


add_shout = RunnablePassthrough.assign(shout=shout)

# ⑤ Join them. The input is {"name": ...}; the output is {"original", "upper", "length", "shout"}.
chain = prompt | to_text | side_by_side | add_shout

# ⑥ Run it, but only when this file is run directly (python hello.py), not when main.py imports it.
if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    print(json.dumps(chain.invoke({"name": name}), indent=2))
    print()
    print("The chain's graph (Mermaid; paste it into https://mermaid.live to see the picture):")
    print(chain.get_graph().draw_mermaid())
