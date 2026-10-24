"""
Tests for pipeline.py: the steps it runs and what it prints, with stand-ins for Gemini (tests/fakes.py), and that
it's the only file that runs anything. Without a key, it stops with a message instead: test_models.py checks that.
"""
from pathlib import Path

from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from pipeline import QUESTION, main

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def test_the_pipeline_retrieves_answers_from_the_chunks_found_then_asks_gemini_alone(capsys):
    stand_in = KeywordEmbeddings()
    model = FakeListChatModel(responses=["In Q2.", "I can't know that."])     # the chain's reply, then the alone one
    main(embeddings=stand_in, model=model, size=SIZE)
    printed = capsys.readouterr().out
    assert stand_in.calls == [("documents", 28), ("query", QUESTION)]    # the chunks, then the question, once each
    assert printed.startswith("Step 1: Read the knowledge base: 10 documents\n"
                              "Step 2: Chunk: 28 chunks of at most 512 characters\n"
                              f"Step 3: Embed: 28 vectors of {SIZE} numbers\n"
                              "Step 4: Store: 28 points, in Qdrant in memory\n"
                              "Step 5: Retrieve and answer\n"
                              f"Question: {QUESTION}\n\n"
                              "What Gemini got: the chain's prompt, filled in with the 5 chunks found and the "
                              "question\n--- system message ---\n")
    assert f"\n--- human message ---\n{QUESTION}\n\nAnswer (Gemini's, asked to use only the chunks found):\n" \
           "In Q2.\n\nSources (the articles of the chunks found, closest first):\n" in printed
    assert printed.endswith("\nFor comparison, the same question to Gemini alone, with no articles:\n"
                            "I can't know that.\n")


def test_the_printed_prompt_is_exactly_what_the_model_got(capsys):
    seen = []

    def stand_in_model(model_input):             # takes the model's place, and keeps what it was given
        seen.append(model_input)
        return AIMessage(content="An answer.")

    main(embeddings=KeywordEmbeddings(), model=RunnableLambda(stand_in_model), size=SIZE)
    printed = capsys.readouterr().out
    system, human = seen[0].to_messages()        # the chain's call: the filled-in prompt
    assert f"--- system message ---\n{system.content}\n--- human message ---\n{human.content}\n" in printed
    assert seen[1] == QUESTION                   # alone: the question, and nothing else


def test_a_question_of_your_own(capsys):
    stand_in = KeywordEmbeddings()
    main("my printer is missing", embeddings=stand_in, model=FakeListChatModel(responses=["x"]), size=SIZE)
    assert stand_in.calls[1:] == [("query", "my printer is missing")]
    assert "\nQuestion: my printer is missing\n" in capsys.readouterr().out


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
