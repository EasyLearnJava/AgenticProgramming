# Step 2: wrap the user's question in a prompt that tells the model how to answer.
# Next: 03_hardcoded_context.py

from langchain_ollama import OllamaLLM

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"

llm = OllamaLLM(model=CHAT_MODEL, base_url=OLLAMA)

# Instructions that tell the model how to answer
instructions = """Answer the question in two sentences or fewer, in plain language.
If you are not sure of the answer, say "I don't know"."""

# 2. Ask the model to generate a response
def ask_generate(prompt):
    return llm.invoke(prompt)

# 3. Put the instructions and the question together in one prompt
def build_prompt(question):
    return f"""{instructions}

Question: {question}"""

# print(build_prompt("When does the library open?"))

# 4. Keep accepting questions
while True:
    question = input("Ask (or type 'exit'): ").strip()

    if question.lower() == "exit":
        break

    if not question:
        continue

    # Build the prompt and show what is being sent to the model
    prompt = build_prompt(question)
    print(f"\nBelow is the prompt sent to LLM \n{prompt}\n")

    # Generate and display the answer
    answer = ask_generate(prompt)
    print(f"\n{answer}\n")

##-----------
# Question: Write a simple poem
# Answer (first run):
#   Here's a short one:
#
#   The sun sets slow and low,
#   A fiery sky to see it grow.
#
# Step 1 gave an eight-line poem for the same question. Here the instructions say "two sentences or fewer",
# so the model shortened the poem to two lines. The prompt changes the answer, not just the question.
# Asked again, it gave a different two-line poem, because the model picks each word with some randomness.
