"""
Tests for pipeline.py: the CSV file read into 10 Documents, with each article's text and labels kept apart; the 10
articles cut into chunks, each no longer than the chunk size, each keeping its article's metadata and where in the
article it starts; the embedding model's name and size, and that every script stops with a clear message when there
is no key; the 28 chunks embedded in one call, one vector each, in order, from their text only; the collection,
storing the 28 chunks with their vectors, and what each stored point holds; the retriever as a Runnable (invoke,
batch, k), finding the closest chunks, closest first, and the chunks formatted for a prompt; and the steps it runs
and what it prints, and that it's the only file that runs anything.

The plain tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory; the live tests
ask the real Gemini.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import SIZE, KeywordEmbeddings
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from pipeline import (CHUNK_OVERLAP, CHUNK_SIZE, COLLECTION, EMBEDDING_MODEL, EMBEDDING_SIZE, KB_FILE, QUESTIONS,
                      TOP_K, KBLoader, embed_chunks, embeddings, format_docs, load_documents, main, make_retriever,
                      make_vector_store, split_documents, store_vectors)

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
SCRIPTS = ["pipeline.py"]
DOCS = load_documents()
CHUNKS = split_documents(DOCS)
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


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


# --- The vector store ---

def test_a_new_store_has_an_empty_cosine_collection_of_the_right_size():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    params = store.client.get_collection(COLLECTION).config.params.vectors
    assert (params.size, params.distance) == (SIZE, Distance.COSINE)
    assert store.client.count(COLLECTION).count == 0


def test_storing_the_vectors_makes_28_points_with_no_call_to_the_model():
    stand_in = KeywordEmbeddings()
    store = make_vector_store(stand_in, SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    assert store.client.count(COLLECTION).count == 28
    assert stand_in.calls == []                                   # the vectors were made before: nothing is embedded


def test_a_chunk_without_a_vector_stops_it_instead_of_being_left_out():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    with pytest.raises(ValueError):
        store_vectors(store, CHUNKS, VECTORS[:27])                # 28 chunks, 27 vectors
    assert store.client.count(COLLECTION).count == 0              # nothing stored, not 27 of the 28


def test_each_point_holds_a_vector_the_chunks_text_and_its_labels():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == SIZE for point in points)
    assert sorted(point.payload["page_content"] for point in points) == sorted(chunk.page_content for chunk in CHUNKS)
    assert {"doc_id", "title", "system", "category", "start_index"} <= set(points[0].payload["metadata"])


def test_the_store_gives_the_points_back_as_the_chunks():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    found = store.similarity_search_by_vector(VECTORS[0], k=1)[0]    # the closest point to chunk 1's own vector
    assert found.page_content == CHUNKS[0].page_content
    assert CHUNKS[0].metadata.items() <= found.metadata.items()       # its labels, as LangChain reads them


def test_an_existing_collection_is_deleted_and_made_new():
    client = QdrantClient(":memory:")
    store_vectors(make_vector_store(KeywordEmbeddings(), SIZE, client), CHUNKS, VECTORS)
    make_vector_store(KeywordEmbeddings(), 5, client)             # the same name again, with another vector size
    assert client.count(COLLECTION).count == 0                    # none of the old points are left
    assert client.get_collection(COLLECTION).config.params.vectors.size == 5      # and it has the new settings


@pytest.mark.live
def test_live_the_28_chunks_are_stored_with_768_number_vectors():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store_vectors(store, CHUNKS, embed_chunks(CHUNKS, embeddings))
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == EMBEDDING_SIZE for point in points)


# --- The retriever ---

def filled_store(stand_in=None):
    store = make_vector_store(stand_in or KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    return store


def test_invoke_gives_the_k_closest_chunks_closest_first():
    assert TOP_K == 5
    chunks = make_retriever(filled_store()).invoke("My VPN won't connect")
    assert len(chunks) == 5
    assert chunks[0].metadata["title"] == "VPN Connection Timeout"


def test_the_retriever_finds_the_same_chunks_as_the_search_by_hand():
    stand_in = KeywordEmbeddings()
    store = filled_store(stand_in)
    by_hand = store.similarity_search_with_score_by_vector(stand_in.embed_query("the printer is missing"), k=TOP_K)
    found = make_retriever(store).invoke("the printer is missing")
    assert [chunk.page_content for chunk in found] == [chunk.page_content for chunk, _ in by_hand]


def test_k_sets_how_many_chunks_come_back():
    assert len(make_retriever(filled_store(), k=2).invoke("My VPN won't connect")) == 2


def test_batch_answers_each_question_in_order_with_one_query_call_each():
    stand_in = KeywordEmbeddings()
    results = make_retriever(filled_store(stand_in)).batch(["my vpn drops", "the printer is missing"])
    assert [chunks[0].metadata["title"] for chunks in results] == ["VPN Connection Timeout", "Printer Not Found"]
    assert sorted(call for call in stand_in.calls if call[0] == "query") == [("query", "my vpn drops"),
                                                                            ("query", "the printer is missing")]


def test_format_docs_numbers_and_titles_each_chunk():
    chunks = make_retriever(filled_store()).invoke("My VPN won't connect")[:2]
    text = format_docs(chunks)
    assert text.startswith("[1] VPN Connection Timeout\n" + chunks[0].page_content)
    assert f"\n\n[2] {chunks[1].metadata['title']}\n{chunks[1].page_content}" in text


@pytest.mark.live
def test_live_the_sample_questions_find_their_articles():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store_vectors(store, CHUNKS, embed_chunks(CHUNKS, embeddings))
    results = make_retriever(store).batch(QUESTIONS)
    assert [chunks[0].metadata["title"] for chunks in results] == [
        "VPN Connection Timeout", "MFA Setup Failure", "Laptop Performance Degradation"]


# --- Running it ---

def test_the_pipeline_embeds_the_chunks_then_the_question_once_through_the_retriever(capsys):
    stand_in = KeywordEmbeddings()
    main(embeddings=stand_in, size=SIZE)
    printed = capsys.readouterr().out
    question = QUESTIONS[0]
    assert stand_in.calls == [("documents", 28), ("query", question)]
    assert printed.startswith("Step 1: Read the knowledge base: 10 documents\n"
                              "Step 2: Chunk: 28 chunks of at most 512 characters\n"
                              f"Step 3: Embed: 28 vectors of {SIZE} numbers\n"
                              "Step 4: Store: 28 points, in Qdrant in memory\n"
                              "Step 5: Retrieve\n"
                              f"Question: {question}\n\nThe 5 closest chunks the retriever found, closest first:\n")
    assert ("\n\nA sample of what a prompt gets: the first 2 of the 5 chunks, as one text (format_docs):\n[1] "
            in printed)


def test_a_question_of_your_own(capsys):
    stand_in = KeywordEmbeddings()
    main("my email bounced", embeddings=stand_in, size=SIZE)
    assert stand_in.calls[1:] == [("query", "my email bounced")]
    assert "\nQuestion: my email bounced\n" in capsys.readouterr().out


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # config.py and utils.py only define what it uses
