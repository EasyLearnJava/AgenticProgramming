"""
Tests for pipeline.py: the steps it runs and what it prints, with KeywordEmbeddings, a stand-in for Gemini
(tests/fakes.py), and that it's the only file that runs anything. Without a key, it stops with a message instead:
test_models.py checks that.
"""
from pathlib import Path

from fakes import KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from pipeline import main
from utils import print_vectors

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def test_the_pipeline_embeds_the_chunks_in_one_call_and_never_a_question(capsys):
    stand_in = KeywordEmbeddings()
    main(embeddings=stand_in)
    printed = capsys.readouterr().out
    assert stand_in.calls == [("documents", 28)]              # one call for the chunks, and no embed_query: no question
    chunks = split_documents(load_documents())
    print_vectors(chunks, embed_chunks(chunks, KeywordEmbeddings()))
    assert printed == ("Step 1: Read the knowledge base: 10 documents\n"
                       "Step 2: Chunk: 28 chunks of at most 512 characters\n"
                       "Step 3: Embed\n" + capsys.readouterr().out)


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
