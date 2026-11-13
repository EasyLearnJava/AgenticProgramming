# Step 1: send a question to the LLM through LangChain and print its response.
# Next: 02_add_prompt.py

from langchain_ollama import OllamaLLM

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"

llm = OllamaLLM(model=CHAT_MODEL, base_url=OLLAMA)

# 2. Ask the model to generate a response
def ask_generate(prompt):
    return llm.invoke(prompt)

# 3. Keep accepting questions
while True:
    question = input("Ask (or type 'exit'): ").strip()

    if question.lower() == "exit":
        break

    if not question:
        continue

    # Generate and display the answer
    answer = ask_generate(question)
    print(f"\n{answer}\n")

##-----------
# Question: What is the capital of the USA?
# Answer:   "The capital of the United States of America (USA) is Washington, D.C."
#
# The model knows this from its training data. Facts that don't change are answered well.

##-----------
# Question: What is the current date and time?
# Answer:   "I'm not capable of providing real-time information or updates. ... my knowledge cutoff
#            is December 2023, but I don't have real-time access to current information."
#
# The model only knows what was in its training data, which stops at its cutoff date.
# It has no clock and no internet, so anything current (today's date, news, prices) must be given to it in the prompt.

##-----------
# Question: Write a simple poem
# Answer (first run):
#   The sun sets slow and low,
#   Painting the sky with colors that glow.
#   Golden hues of orange bright,
#   Fade to pink, and purple in sight.
#   ...
#
# The model writes new text, not just facts. Asked again, it gave a different poem with some of the
# same lines, because the model picks each word with some randomness.
