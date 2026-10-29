"""
Tests for src/ingestion/loader.py: the 10 articles as Documents, each with its text in sections and its labels and
where it came from as metadata; the loader reading nothing until load(); and each way a file can be unusable,
stopping with a message that names the file, and every bad row with its row and line.
"""
import pytest

from src.config.settings import PROJECT_DIR
from src.exceptions import IngestionError
from src.ingestion import loader as loader_module
from src.ingestion.loader import KBLoader

KB_FILE = PROJECT_DIR / "data" / "sample_it_kb.csv"
HEADER = "title,problem,resolution,system,category,notes,priority,tags"
COLUMNS = {"text_columns": ["title", "problem", "resolution", "notes"],
           "metadata_columns": ["title", "system", "category", "priority", "tags"],
           "required_columns": ["title", "problem", "resolution"]}


def loader_for(path) -> KBLoader:
    return KBLoader(path, **COLUMNS)


def write(tmp_path, text: str, encoding: str = "utf-8"):
    path = tmp_path / "kb.csv"
    path.write_text(text, encoding=encoding)
    return path


# --- The Documents ---

def test_one_document_per_article_with_its_text_in_sections():
    docs = loader_for(KB_FILE).load()
    assert len(docs) == 10
    for doc in docs:
        sections = doc.page_content.split("\n\n")
        assert [section.split(": ", 1)[0] for section in sections] == ["Title", "Problem", "Resolution", "Notes"]


def test_the_labels_and_where_it_came_from_are_metadata():
    first = loader_for(KB_FILE).load()[0]
    assert first.metadata == {"doc_id": "0", "source": "sample_it_kb.csv", "title": "VPN Connection Timeout",
                              "system": "VPN", "category": "Remote Access", "priority": "High",
                              "tags": "vpn;timeout;remote;connection"}
    assert "Priority:" not in first.page_content


def test_making_the_loader_reads_nothing(tmp_path):
    loader = loader_for(tmp_path / "missing.csv")     # no error yet: the loader hasn't opened the file
    with pytest.raises(IngestionError):
        loader.load()                                 # load() is what opens it


def test_a_bom_and_spaces_in_the_header_are_cleaned_and_values_trimmed(tmp_path):
    path = write(tmp_path, "﻿title, problem ,resolution,system,category,notes,priority,tags\n"
                           " VPN ,Drops,Restart it,VPN,Remote Access,,High,vpn\n")
    doc = loader_for(path).load()[0]
    assert doc.page_content == "Title: VPN\n\nProblem: Drops\n\nResolution: Restart it\n\nNotes: "
    assert doc.metadata["title"] == "VPN"


def test_the_load_is_logged_as_a_span(logs):
    loader_for(KB_FILE).load()
    record = logs.find("ingestion.load ok")
    assert (record.file, record.documents) == ("sample_it_kb.csv", 10)


# --- A file that can't be used ---

def test_a_missing_file_names_the_full_path(tmp_path):
    with pytest.raises(IngestionError, match=r"Knowledge base file not found: .*missing\.csv"):
        loader_for(tmp_path / "missing.csv").load()


@pytest.mark.parametrize("text, message", [
    ("", "is empty, with no header row"),
    (HEADER + "\n", "has a header row but no articles"),
    ("title,problem,resolution,system,category,notes,priority\nA,B,C,D,E,F,G\n", r"is missing columns \(tags\)"),
], ids=["empty", "header only", "missing column"])
def test_an_unusable_file_says_why(tmp_path, text, message):
    with pytest.raises(IngestionError, match=message):
        loader_for(write(tmp_path, text)).load()


def test_a_file_that_cant_be_opened_says_why(tmp_path, monkeypatch):
    path = write(tmp_path, HEADER + "\nA,B,C,D,E,F,G,H\n")

    def no_permission(file, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(file))

    monkeypatch.setattr(loader_module, "open", no_permission, raising=False)      # open(), as the loader sees it
    with pytest.raises(IngestionError, match=r"can't be opened \(Permission denied\): .*kb\.csv"):
        loader_for(path).load()


def test_a_file_that_isnt_utf8_says_so(tmp_path):
    path = write(tmp_path, HEADER + "\nA,B,C,D,E,F,G,H\n", encoding="utf-16")
    with pytest.raises(IngestionError, match=r"isn't utf-8 text .*Save it as UTF-8"):
        loader_for(path).load()


def test_every_bad_row_is_listed_with_its_row_and_line_and_nothing_is_read(tmp_path, logs):
    path = write(tmp_path, HEADER + "\n"
                 "VPN,Drops,Restart it,VPN,Remote Access,,High,vpn\n"        # row 0: good
                 "MFA,Fails,,MFA,Identity,,High,mfa\n"                        # row 1: no resolution
                 "Printer,Gone,Re-add it,Printer,Hardware,Notes, with a comma,Low,printer\n"   # row 2: 9 fields
                 "\n"                                                         # a blank line: skipped by the reader
                 "Email,Too big,Zip it\n")                                    # row 3: 3 fields
    with pytest.raises(IngestionError) as caught:
        loader_for(path).load()
    assert str(caught.value).startswith(
        "Knowledge base file has 3 row(s) that can't be read: row 1 (line 3): no value for resolution; "
        "row 2 (line 4): 9 fields, but the header has 8; row 3 (line 6): 3 fields, but the header has 8. Fix them in ")
    assert logs.find("ingestion.load failed").error_type == "IngestionError"


def test_a_long_list_of_bad_rows_is_shortened(tmp_path):
    path = write(tmp_path, HEADER + "\n" + "A,B,,D,E,F,G,H\n" * 8)
    with pytest.raises(IngestionError, match=r"has 8 row\(s\) .*row 4 \(line 6\): no value for resolution; and 3 more"):
        loader_for(path).load()
