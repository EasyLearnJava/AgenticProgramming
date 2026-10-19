"""
Project 3: the same chain as project 2, unchanged. What changes is the page (index.html): it asks the server to
run the chain only when you click a button.

    prompt (PromptTemplate: the text)  |  to_text (RunnableLambda: StringPromptValue -> str)

Run it on its own:   python hello.py   ->   Hello World, welcome to LangChain!
main.py imports `chain` from here and serves it at GET /api/hello.
"""
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

# ① The template: the text we want to show.
prompt = PromptTemplate.from_template("Hello World, welcome to LangChain!")

# ② The converter: the prompt gives back an object (a StringPromptValue), this turns it into text.
to_text = RunnableLambda(lambda value: value.to_string())

# ③ Join them: prompt first, then to_text. `a | b` is Python's a.pipe(b).
chain = prompt | to_text

# ④ Run it, but only when this file is run directly (python hello.py), not when main.py imports it.
if __name__ == "__main__":
    answer = chain.invoke({})
    print(answer)
