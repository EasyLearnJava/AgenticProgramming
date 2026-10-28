"""
Tests for pipeline.py: the CSV file read into 10 Documents, with each article's text and labels kept apart; the 10
articles cut into chunks, each no longer than the chunk size, each keeping its article's metadata and where in the
article it starts; the embedding model's name and size, and that every script stops with a clear message when there
is no key; the 28 chunks embedded in one call, one vector each, in order, from their text only; and the steps it runs
and what it prints, and that it's the only file that runs anything.

The plain tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py); the live tests ask the real Gemini.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import SIZE, KeywordEmbeddings
from langchain_core.documents import Document

from pipeline import (CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL, EMBEDDING_SIZE, KB_FILE, KBLoader, embed_chunks,
                      embeddings, load_documents, main, split_documents)
from utils import print_vectors

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
SCRIPTS = ["pipeline.py"]
DOCS = load_documents()
CHUNKS = split_documents(DOCS)


# --- The Documents ---

def test_one_document_per_article():
    assert KB_FILE == FOLDER / "data" / "sample_it_kb.csv"
    assert len(DOCS) == 10
    assert all(isinstance(doc, Document) for doc in DOCS)


def test_the_text_has_title_problem_resolution_and_notes_in_order():
    for doc in DOCS:
        sections = doc.page_content.split("\n\n")
        assert [section.split(": ", 1)[0] for section in sections] == ["Title", "Problem", "Resolution", "Notes"]
        assert all(section.split(": ", 1)[1].strip() for section in sections)     # no section is empty


def test_the_labels_are_metadata_not_text():
    assert DOCS[0].metadata == {"doc_id": "0", "title": "VPN Connection Timeout", "system": "VPN",
                                "category": "Remote Access", "priority": "High",
                                "tags": "vpn;timeout;remote;connection"}
    assert [doc.metadata["doc_id"] for doc in DOCS] == [str(n) for n in range(10)]
    for doc in DOCS:
        assert "System:" not in doc.page_content and "Priority:" not in doc.page_content


def test_making_the_loader_reads_nothing_and_load_reads_the_file(tmp_path):
    loader = KBLoader(tmp_path / "missing.csv")    # no error yet: the loader hasn't opened the file
    with pytest.raises(FileNotFoundError):
        loader.load()                              # load() is what opens it


# --- The chunks ---

def test_512_characters_cut_each_article_into_2_or_3_chunks():
    assert (CHUNK_SIZE, CHUNK_OVERLAP) == (512, 50)
    chunks = split_documents(DOCS)
    assert len(chunks) == 28
    per_article = [sum(c.metadata["doc_id"] == d.metadata["doc_id"] for c in chunks) for d in DOCS]
    assert set(per_article) == {2, 3}


@pytest.mark.parametrize("size", [200, 512, 1000])
def test_no_chunk_is_longer_than_the_chunk_size(size):
    assert all(len(chunk.page_content) <= size for chunk in split_documents(DOCS, chunk_size=size))


def test_each_chunk_keeps_its_articles_metadata_and_where_it_starts():
    by_id = {doc.metadata["doc_id"]: doc for doc in DOCS}
    for chunk in split_documents(DOCS):
        article = by_id[chunk.metadata["doc_id"]]
        start = chunk.metadata["start_index"]
        assert {k: v for k, v in chunk.metadata.items() if k != "start_index"} == article.metadata
        assert article.page_content[start:start + len(chunk.page_content)] == chunk.page_content


def test_chunks_break_between_sections_first():
    # The empty lines between Title, Problem, Resolution and Notes are the first places the splitter tries.
    for chunk in split_documents(DOCS):
        assert chunk.page_content.split(": ", 1)[0] in {"Title", "Problem", "Resolution", "Notes"}


def test_1000_characters_keep_every_article_whole():
    chunks = split_documents(DOCS, chunk_size=1000)
    assert [chunk.page_content for chunk in chunks] == [doc.page_content for doc in DOCS]


# --- The model ---

def test_the_embedding_model_and_its_vector_size():
    assert embeddings.model == EMBEDDING_MODEL == "gemini-embedding-001"
    assert embeddings.output_dimensionality == EMBEDDING_SIZE == 768


@pytest.mark.parametrize("script", SCRIPTS)
def test_without_a_key_each_script_stops_with_the_message_not_a_stack_trace(script):
    # A copy of this process's environment, with GOOGLE_API_KEY set to "". An empty key also stops .env from being
    # used: load_dotenv() never overwrites a variable that is already set.
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, script], cwd=FOLDER, env=env, capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 1
    assert "Can't build the models: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.live
def test_live_an_embedding_has_768_numbers():
    assert len(embeddings.embed_documents(["Title: VPN Connection Timeout"])[0]) == 768


# --- The embedding ---

class RecordingEmbeddings(KeywordEmbeddings):
    """KeywordEmbeddings that also keeps the texts it was given."""

    def embed_documents(self, texts):
        self.texts = list(texts)
        return super().embed_documents(texts)


def test_the_28_chunks_are_embedded_in_one_call_one_vector_each():
    stand_in = KeywordEmbeddings()
    vectors = embed_chunks(CHUNKS, stand_in)
    assert len(vectors) == 28
    assert all(len(vector) == SIZE for vector in vectors)
    assert stand_in.calls == [("documents", 28)]


def test_only_the_chunks_text_is_sent_in_the_chunks_order():
    stand_in = RecordingEmbeddings()
    vectors = embed_chunks(CHUNKS, stand_in)
    assert stand_in.texts == [chunk.page_content for chunk in CHUNKS]               # the text, not the labels
    assert vectors == [KeywordEmbeddings().embed_documents([chunk.page_content])[0] for chunk in CHUNKS]


@pytest.mark.live
def test_live_every_chunk_gets_768_numbers():
    vectors = embed_chunks(CHUNKS, embeddings)
    assert len(vectors) == 28
    assert all(len(vector) == EMBEDDING_SIZE for vector in vectors)


# --- Running it ---

def test_the_pipeline_embeds_the_chunks_in_one_call_and_never_a_question(capsys):
    stand_in = KeywordEmbeddings()
    main(embeddings=stand_in)
    printed = capsys.readouterr().out
    assert stand_in.calls == [("documents", 28)]              # one call for the chunks, and no embed_query: no question
    print_vectors(CHUNKS, embed_chunks(CHUNKS, KeywordEmbeddings()), EMBEDDING_MODEL)
    assert printed == ("Step 1: Read the knowledge base: 10 documents\n"
                       "Step 2: Chunk: 28 chunks of at most 512 characters\n"
                       "Step 3: Embed\n" + capsys.readouterr().out)


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # config.py and utils.py only define what it uses
