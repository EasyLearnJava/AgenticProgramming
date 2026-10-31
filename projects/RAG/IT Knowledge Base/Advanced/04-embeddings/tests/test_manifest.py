"""
Tests for manifest.py: the first run passes everything on; later runs pass on only the articles added or changed (and
say which fields changed), list the removed ones for deletion, and never take a row skipped this run for a removed
article; the manifest is written whole or not at all, and a broken one says what to do.
"""
import json

import pytest
from langchain_core.documents import Document

from manifest import Manifest


def doc(the_id: str, row: int, title: str = "") -> Document:
    return Document(page_content=f"Title: {title or the_id}", metadata={"doc_id": the_id, "title": title or the_id,
                                                                      "row": row})


DOCS = [doc("kb-a", 0, "VPN"), doc("kb-b", 1, "MFA"), doc("kb-c", 2, "Printer")]
FINGERPRINTS = {"kb-a": {"title": "1", "resolution": "2"}, "kb-b": {"title": "3", "resolution": "4"},
                "kb-c": {"title": "5", "resolution": "6"}}


@pytest.fixture
def manifest(tmp_path):
    """A manifest saved from DOCS, as a first run leaves it."""
    saved = Manifest(tmp_path / "manifest.json")
    saved.write(DOCS, FINGERPRINTS)
    return saved


def test_no_manifest_is_a_first_run_and_everything_is_new(tmp_path):
    changes = Manifest(tmp_path / "none.json").compare(DOCS, FINGERPRINTS)
    assert changes.first_run and changes.added == DOCS and changes.passed_on() == DOCS


def test_an_unchanged_file_passes_nothing_on(manifest):
    changes = manifest.compare(DOCS, FINGERPRINTS)
    assert (changes.passed_on(), changes.unchanged, changes.removed) == ([], DOCS, [])


def test_added_changed_and_removed_are_each_found(manifest):
    now = [DOCS[0], doc("kb-d", 1, "Keyboard"), DOCS[1]]                     # kb-c gone, kb-d new
    fingerprints = {**FINGERPRINTS, "kb-b": {"title": "3", "resolution": "changed"}, "kb-d": {"title": "7"}}
    changes = manifest.compare(now, fingerprints)
    assert [d.metadata["doc_id"] for d in changes.added] == ["kb-d"]
    assert [(d.metadata["doc_id"], fields) for d, fields in changes.changed] == [("kb-b", ["resolution"])]
    assert [d.metadata["doc_id"] for d in changes.unchanged] == ["kb-a"]
    assert changes.removed == [("kb-c", "Printer")]
    assert [d.metadata["doc_id"] for d in changes.passed_on()] == ["kb-d", "kb-b"]    # in the file's order


def test_a_field_added_or_dropped_counts_as_a_change(manifest):
    fingerprints = {**FINGERPRINTS, "kb-a": {"title": "1", "resolution": "2", "notes": "8"},
                    "kb-b": {"title": "3"}}
    changes = manifest.compare(DOCS, fingerprints)
    assert [(d.metadata["doc_id"], fields) for d, fields in changes.changed] == [("kb-a", ["notes"]),
                                                                                ("kb-b", ["resolution"])]


def test_a_row_skipped_this_run_is_held_not_removed_and_its_entry_kept(manifest):
    changes = manifest.compare(DOCS[:2], FINGERPRINTS, held={"kb-c": "Printer"})
    assert (changes.removed, changes.held) == ([], [("kb-c", "Printer")])
    manifest.write(DOCS[:2], FINGERPRINTS, keep=("kb-c",))
    assert set(manifest.read()) == {"kb-a", "kb-b", "kb-c"}                  # its last version stays


def test_full_passes_everything_on_without_reading_the_manifest(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    changes = Manifest(broken).compare(DOCS, FINGERPRINTS, full=True)
    assert changes.full and changes.passed_on() == DOCS


def test_the_manifest_holds_each_articles_title_and_field_hashes(manifest):
    data = json.loads(manifest.path.read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["saved_at"].endswith("+00:00")
    assert data["articles"]["kb-a"] == {"title": "VPN", "fields": {"title": "1", "resolution": "2"}}


@pytest.mark.parametrize("text, why", [
    ("not json", "JSONDecodeError"),
    ('{"version": 2, "articles": {}}', "layout 2, not 1"),
    ('{"version": 1}', "KeyError"),
    ('{"version": 1, "articles": {"kb-a": {"title": 1, "fields": {}}}}', "an article without a title or fields"),
])
def test_a_broken_manifest_says_what_to_do(tmp_path, text, why):
    path = tmp_path / "manifest.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=f"The manifest can't be read .*{why}.*Delete it, or run with --full"):
        Manifest(path).compare(DOCS, FINGERPRINTS)


def test_a_manifest_that_cant_be_written_leaves_nothing_behind(tmp_path):
    folder = tmp_path / "manifest.json"
    folder.mkdir()                                                          # a folder where the file should go
    with pytest.raises(ValueError, match="The manifest can't be saved"):
        Manifest(folder).write(DOCS, FINGERPRINTS)
    assert [path.name for path in tmp_path.iterdir()] == ["manifest.json"]  # no temporary file left
