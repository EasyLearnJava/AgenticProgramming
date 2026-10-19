"""
Project 4: the chain takes one input, a name. The template has a variable, {name}, filled in on every call.

    prompt (PromptTemplate: "Hello {name}, ...")  |  to_text (RunnableLambda: PromptValue -> str)

Run it on its own:   python hello.py         ->   Hello World, welcome to LangChain!
                     python hello.py Raghu   ->   Hello Raghu, welcome to LangChain!
main.py imports `chain` from here and serves it at POST /api/hello.
"""
import sys

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

# ① The template: the text we want to show, with a {name} slot. prompt.input_variables is ["name"].
prompt = PromptTemplate.from_template("Hello {name}, welcome to LangChain!")

# ② The converter: the prompt gives back an object (a StringPromptValue), this turns it into text.
to_text = RunnableLambda(lambda value: value.to_string())

# ③ Join them: prompt first, then to_text. `a | b` is Python's a.pipe(b).
chain = prompt | to_text

# ④ Run it, but only when this file is run directly (python hello.py), not when main.py imports it.
#    The input is now a dict with one key per template variable: {"name": "..."}.
if __name__ == "__main__":
    # sys.argv is the command line as a list: python hello.py Raghu -> ["hello.py", "Raghu"]. Item [0] is the
    # file's name, so the name you typed is [1]; with nothing after the file name, it's "World". Quote a name
    # with a space in it ("Raghu S"): unquoted, each word is its own item and only the first one is used.
    name = sys.argv[1] if len(sys.argv) > 1 else "World"
    answer = chain.invoke({"name": name})
    print(answer)
