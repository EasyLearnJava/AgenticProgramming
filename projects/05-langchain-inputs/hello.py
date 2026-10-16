"""
Project 5: the chain takes several inputs (a greeting, a name and a city), and the greeting has a default.

    prompt.partial(greeting="Hello")  |  to_text (RunnableLambda: PromptValue -> str)

Run it on its own:   python hello.py                              ->   Hello Raghu from Dallas, welcome to LangChain!
                     python hello.py Asha Pune                    ->   Hello Asha from Pune, welcome to LangChain!
                     python hello.py Asha Pune "Good morning"     ->   Good morning Asha from Pune, welcome to LangChain!
main.py imports `chain` from here and serves it at POST /api/hello.
"""
import sys

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

# ① The template, with three slots. prompt.input_variables is ["city", "greeting", "name"].
prompt = PromptTemplate.from_template("{greeting} {name} from {city}, welcome to LangChain!")

# ② partial() fills one slot in ahead of time and gives back a new prompt; the original is unchanged.
#    Its input_variables is ["city", "name"]: greeting is no longer required, but a greeting passed in still wins.
prompt_with_default = prompt.partial(greeting="Hello")

# ③ The converter: the prompt gives back an object (a StringPromptValue), this turns it into text.
to_text = RunnableLambda(lambda value: value.to_string())

# ④ Join them: the prompt with the default greeting first, then to_text.
chain = prompt_with_default | to_text

# ⑤ Run it, but only when this file is run directly (python hello.py), not when main.py imports it.
#    The input is a dict with one key per variable; leave "greeting" out to get the default.
if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    city = sys.argv[2] if len(sys.argv) > 2 else "Dallas"
    inputs = {"name": name, "city": city}
    if len(sys.argv) > 3:
        inputs["greeting"] = sys.argv[3]
    print(chain.invoke(inputs))
