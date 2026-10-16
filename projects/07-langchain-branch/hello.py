"""
Project 7: branch and batch. A RunnableBranch sends each input down one of two paths (formal or casual), and
batch() runs a whole list of inputs in one call.

    RunnableBranch((is_formal, formal_chain), casual_chain)

Run it on its own:   python hello.py                 ->   one greeting in each style, then a batch of five
                     python hello.py Asha formal     ->   Good day, Asha. Welcome to LangChain.
main.py imports `chain` from here and serves it at POST /api/hello (one input) and POST /api/batch (a list).
"""
import sys

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableBranch, RunnableLambda

# ① The converter, shared by both paths: the prompt gives back a StringPromptValue, this turns it into text.
to_text = RunnableLambda(lambda value: value.to_string(), name="to_text")

# ② Two paths: the same idea as before, one chain per style.
formal_chain = PromptTemplate.from_template("Good day, {name}. Welcome to LangChain.") | to_text
casual_chain = PromptTemplate.from_template("Hey {name}! Welcome to LangChain!") | to_text


# ③ The condition: gets the whole input and says True or False.
def is_formal(inputs: dict) -> bool:
    return inputs["style"] == "formal"


# ④ The branch: (condition, path) pairs, checked in order; the first true one picks the path.
#    The last argument, on its own, is the default: used when no condition is true.
chain = RunnableBranch(
    (is_formal, formal_chain),
    casual_chain,
)


# ⑤ The same thing without LangChain, to compare: a plain if. It gives the same text, but it is not a Runnable,
#    so it has no .batch(), .ainvoke() or .astream(), and you can't pipe it into anything.
def greet_with_if(inputs: dict) -> str:
    if inputs["style"] == "formal":
        return f"Good day, {inputs['name']}. Welcome to LangChain."
    return f"Hey {inputs['name']}! Welcome to LangChain!"


# ⑥ Run it, but only when this file is run directly (python hello.py), not when main.py imports it.
if __name__ == "__main__":
    if len(sys.argv) > 2:
        print(chain.invoke({"name": sys.argv[1], "style": sys.argv[2]}))
    else:
        print(chain.invoke({"name": "Raghu", "style": "formal"}))
        print(chain.invoke({"name": "Raghu", "style": "casual"}))
        print()
        # batch(): a list in, a list out, in the same order. max_concurrency: at most 3 run at the same time.
        people = [
            {"name": "Raghu", "style": "formal"},
            {"name": "Asha", "style": "casual"},
            {"name": "Ken", "style": "formal"},
            {"name": "Mia", "style": "casual"},
            {"name": "Li", "style": "casual"},
        ]
        for answer in chain.batch(people, config={"max_concurrency": 3}):
            print(answer)
