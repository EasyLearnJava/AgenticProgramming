# Step 3: send a hard-coded context with the question, so the model answers from it.
# Next: 04_full_context.py

from langchain_ollama import OllamaLLM

# 1. Settings
OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.2"

llm = OllamaLLM(model=CHAT_MODEL, base_url=OLLAMA)

# Instructions that tell the model how to answer
instructions = """Answer the question using ONLY the context below.
If the answer isn't in the context, say "I don't know"."""

# A small context written straight into the code (two paragraphs from the handbook)
context = """The library is open from 9am to 8pm Monday through Thursday and from 10am to 6pm on Friday and Saturday. The library is closed on Sundays, New Year's Day, and Labor Day.

Food and drinks are not allowed in the reading rooms, except for water in closed bottles. Visitors may consume other food and drinks in the outdoor courtyard."""

# 2. Ask the model to generate a response
def ask_generate(prompt):
    return llm.invoke(prompt)

# 3. Put the instructions, the context and the question together in one prompt
def build_prompt(context, question):
    return "\n\n".join([instructions, f"Context:\n{context}", f"Question: {question}"])

# 4. Keep accepting questions
while True:
    question = input("Ask (or type 'exit'): ").strip()

    if question.lower() == "exit":
        break

    if not question:
        continue

    # Build the prompt and show what is being sent to the model
    prompt = build_prompt(context, question)
    print(f"\nBelow is the prompt sent to LLM \n{prompt}\n")

    # Generate and display the answer
    answer = ask_generate(prompt)
    print(f"\n{answer}\n")

##-----------
# Question: What is the capital of Delhi?
# Answer:   "I don't know."
#           Second run: "I don't know. The provided context only discusses library hours and policies,
#           but does not mention anything about Delhi or its capital."
#
# The model knows about Delhi from its training data, but the instructions say use ONLY the context.
# The context has nothing about Delhi, so it says "I don't know" instead of answering from memory.

##-----------
# Question: When is the library open?
# Answer:
#   The library is open from:
#   - 9am to 8pm on Monday through Thursday
#   - 10am to 6pm on Friday and Saturday
#   - (No specific time given, so only days are mentioned) Sunday, New Year's Day, and Labor Day are closed.
#
# The answer comes from the context, not from the model's memory: these are our library's hours.
# The third line is muddled. In the second run it read "(no specific hours mentioned) on Sundays,
# New Year's Day, and Labor Day.", which no longer says the library is closed on those days.
# Even with the right context in front of it, a small model can word the answer wrongly.

##-----------
# Ask these questions (each gave the right answer in 3 runs out of 3)
#   What time does the library close on Friday?   -> 6pm
#   Where can visitors eat food?                   -> In the outdoor courtyard.
