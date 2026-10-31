"""
Tests for chunking.py: no chunk crosses a section or passes the token ceiling; every chunk has its header, its
identity and a parent; the same text gets the same chunk ID on every run and in a re-sorted file; and each article in
data/sample_it_kb_chunking.csv (clear sections, a very long fix, a one-line note, repeated paragraphs, a run with no
spaces, a fragment at the end) is cut as it should be, with the report saying what was removed, merged or cut.
"""
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

from chunking import CHUNK_SIZE, MAX_TOKENS, KBTextSplitter
from knowledge_base_loader import KB_FILE, SETTINGS_FILE, KBLoader
from settings import load_settings
from utils import count_tokens

DATA = Path(__file__).resolve().parent.parent / "data"
SETTINGS = load_settings(SETTINGS_FILE)


def load(path: Path) -> list[Document]:
    return KBLoader(path, settings=SETTINGS, clock=lambda: datetime(2026, 10, 30, tzinfo=UTC)).load()


docs = load(KB_FILE)
splitter = KBTextSplitter()
chunks = splitter.split_documents(docs)
cases = load(DATA / "sample_it_kb_chunking.csv")
case_splitter = KBTextSplitter()
case_chunks = case_splitter.split_documents(cases)


def of(title: str, found: list[Document] = case_chunks) -> list[Document]:
    """The chunks of the article with this title, in order."""
    return [chunk for chunk in found if chunk.metadata["title"] == title]


def bodies(found: list[Document]) -> list[str]:
    """Each chunk's text without its header's first line (the title)."""
    return [chunk.page_content.split("\n", 1)[1] for chunk in found]


# -------------------------------------------------
# Every Chunk
# -------------------------------------------------

def test_it_is_a_langchain_text_splitter_with_the_project_sizes():
    assert isinstance(splitter, TextSplitter)
    assert (splitter._chunk_size, splitter._chunk_overlap, splitter.min_tokens, splitter.max_tokens) == \
        (CHUNK_SIZE, 16, 8, MAX_TOKENS) == (SETTINGS.chunking.chunk_size, SETTINGS.chunking.chunk_overlap,
                                           SETTINGS.chunking.min_tokens, SETTINGS.chunking.max_tokens)


def test_the_sample_is_39_chunks_each_with_its_section_in_order():
    assert len(chunks) == 39
    assert [chunk.metadata["section"] for chunk in chunks if chunk.metadata["doc_id"] == docs[0].metadata["doc_id"]] \
        == ["problem", "resolution", "notes"]


def test_no_chunk_crosses_a_section():
    for chunk in chunks + case_chunks:
        label = chunk.metadata["section"].capitalize()
        body = chunk.page_content.split("\n", 1)[1]
        assert body.startswith(f"{label}: ")
        other_labels = {"Problem: ", "Resolution: ", "Notes: "} - {f"{label}: "}
        assert not any(other in body for other in other_labels)


def test_no_chunk_passes_the_ceiling_and_its_count_is_recorded():
    for chunk in chunks + case_chunks:
        assert chunk.metadata["token_count"] == count_tokens(chunk.page_content) <= MAX_TOKENS
    assert max(chunk.metadata["token_count"] for chunk in chunks) <= CHUNK_SIZE


def test_every_chunk_starts_with_its_articles_title_and_its_section():
    first = chunks[0]
    assert first.page_content.startswith("VPN Connection Timeout\nProblem: Users experience timeout errors")
    assert all(chunk.page_content.split("\n", 1)[0] == chunk.metadata["title"] for chunk in chunks)


def test_every_chunk_has_its_identity_and_its_articles_metadata():
    metadata = chunks[1].metadata
    doc_id = docs[0].metadata["doc_id"]
    assert (metadata["doc_id"], metadata["section"], metadata["position"]) == (doc_id, "resolution", 1)
    assert metadata["parent_id"] == f"{doc_id}:resolution"
    assert metadata["chunk_id"].startswith(f"{doc_id}:resolution:") and len(metadata["chunk_id"]) == len(doc_id) + 20
    assert {name: metadata[name] for name in docs[0].metadata} == docs[0].metadata    # labels and provenance kept


def test_chunk_ids_are_unique_and_the_same_on_every_run_and_in_a_re_sorted_file():
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]
    assert len(set(ids)) == len(ids)
    assert [chunk.metadata["chunk_id"] for chunk in KBTextSplitter().split_documents(docs)] == ids
    reordered = KBTextSplitter().split_documents(load(DATA / "sample_it_kb_reordered.csv"))
    assert {chunk.metadata["chunk_id"] for chunk in reordered} == set(ids)


def test_each_section_is_kept_whole_as_its_chunks_parent():
    assert len(splitter.parents) == 30
    for chunk in chunks:
        parent = splitter.parents[chunk.metadata["parent_id"]]
        assert chunk.page_content.split(": ", 1)[1] in parent.page_content
    assert splitter.parents[chunks[0].metadata["parent_id"]].metadata["section"] == "problem"


def test_split_text_gives_the_chunks_texts():
    assert splitter.split_text(docs[0].page_content) == [chunk.page_content for chunk in chunks[:3]]


def test_text_with_no_section_labels_is_one_section():
    found = KBTextSplitter().split_documents([Document(page_content="Restart the router.", metadata={"doc_id": "x"})])
    assert [(chunk.page_content, chunk.metadata["section"]) for chunk in found] == [("Text: Restart the router.",
                                                                                    "text")]


@pytest.mark.parametrize("sizes", [dict(chunk_size=8, min_tokens=8), dict(chunk_size=128, max_tokens=130),
                                   dict(chunk_size=16, chunk_overlap=16)])
def test_sizes_that_cant_work_fail_when_configured(sizes):
    with pytest.raises(ValueError):
        KBTextSplitter(**sizes)


# -------------------------------------------------
# The Chunking Cases, One Article Each
# -------------------------------------------------

def test_an_article_with_clear_sections_is_one_chunk_per_section():
    assert [chunk.metadata["section"] for chunk in of("VPN Connection Timeout")] == ["problem", "resolution", "notes"]


def test_a_very_long_fix_is_cut_into_chunks_between_whole_steps():
    resolution = [chunk for chunk in of("Outlook Keeps Crashing") if chunk.metadata["section"] == "resolution"]
    assert len(resolution) == 4
    assert [body.split(": ", 1)[1].split(" ", 1)[0] for body in bodies(resolution)] == ["1.", "5.", "9.", "13."]
    assert all(body.endswith(".") for body in bodies(resolution))            # no step cut in two


def test_a_one_line_note_is_a_chunk_of_its_own_with_its_header():
    notes = [chunk for chunk in of("Printer Offline After Move") if chunk.metadata["section"] == "notes"]
    assert [chunk.page_content for chunk in notes] == ["Printer Offline After Move\nNotes: After moves."]


def test_a_repeated_paragraph_is_removed_and_reported():
    assert bodies(of("Disk Space Low")) == [
        "Problem: The laptop warns that the C: drive is almost full",
        "Resolution: Delete the files in C:\\Windows\\Temp and empty the Recycle Bin. Move the user's Downloads "
        "folder to OneDrive and keep only recent files on the laptop."]
    assert [(issue.section, issue.message[:30]) for issue in case_splitter.report.removed] == [
        ("resolution", "a paragraph already in resolut"), ("notes", "a paragraph already in resolut")]


def test_a_run_with_no_spaces_is_cut_to_fit_and_reported():
    notes = [chunk for chunk in of("Certificate Error on Intranet") if chunk.metadata["section"] == "notes"]
    assert len(notes) == 4 and all(chunk.metadata["token_count"] <= CHUNK_SIZE for chunk in notes)
    [issue] = case_splitter.report.cut
    assert issue.message == "a 320-token piece with no spaces cut into 3 pieces"


def test_a_fragment_at_the_end_is_merged_into_the_chunk_before_it():
    resolution = [chunk for chunk in of("Phone Enrolment Fails") if chunk.metadata["section"] == "resolution"]
    assert len(resolution) == 1 and resolution[0].page_content.endswith("5. Wait.")
    assert CHUNK_SIZE < resolution[0].metadata["token_count"] <= MAX_TOKENS     # past the size, under the ceiling
    assert [issue.message for issue in case_splitter.report.merged] == [
        "a 4-token piece merged into the chunk before it"]


def test_the_report_counts_the_articles_and_chunks():
    assert (case_splitter.report.articles, case_splitter.report.chunks) == (6, len(case_chunks)) == (6, 22)
    assert splitter.report.has_issues() is False


def test_a_chunk_cut_from_a_repeating_run_isnt_kept_twice():
    cutter = KBTextSplitter()
    found = cutter.split_documents([Document(page_content="Title: Key\n\nNotes: " + "AB" * 800,
                                             metadata={"doc_id": "kb-key"})])
    ids = [chunk.metadata["chunk_id"] for chunk in found]
    assert len(ids) == len(set(ids)) == 2                    # 4 pieces cut; the 2nd and 3rd are the 1st again
    assert [issue.message for issue in cutter.report.removed] == ["a chunk the same as one before it"] * 2
