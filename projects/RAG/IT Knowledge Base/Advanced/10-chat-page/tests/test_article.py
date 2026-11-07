"""
Tests for article.py: the schema an article must fit (required fields, lengths, a priority from four values, tags as
a list, visibility), the error line naming each field that failed, one spelling per label value, and IDs that
survive re-sorting.
"""
import pytest
from pydantic import ValidationError

from article import ARTICLE_FIELDS, REQUIRED_FIELDS, Article, Priority, Spellings, describe, doc_id

GOOD = {"title": "VPN Connection Timeout", "problem": "VPN times out", "resolution": "Restart the client",
        "system": "VPN", "category": "Remote Access", "priority": "High", "tags": "vpn;timeout"}


def failure(**changes) -> str:
    """The one-line description of why GOOD, with these changes, fails the schema."""
    with pytest.raises(ValidationError) as caught:
        Article.model_validate({**GOOD, **changes})
    return describe(caught.value)


# -------------------------------------------------
# The Schema
# -------------------------------------------------

def test_a_good_article_validates_with_typed_labels():
    article = Article.model_validate(GOOD)
    assert (article.priority, article.tags) == (Priority.HIGH, ["vpn", "timeout"])
    assert (article.notes, article.visibility, article.team, article.id) == (None, None, None, None)
    assert article.model_dump(mode="json")["priority"] == "High"


def test_the_fields_and_the_required_ones():
    assert ARTICLE_FIELDS == ("id", "title", "problem", "resolution", "notes", "system", "category", "priority",
                              "tags", "visibility", "team")
    assert REQUIRED_FIELDS == ("title", "problem", "resolution")


def test_a_required_field_must_be_there_and_have_a_value():
    assert failure(problem="   ") == 'problem: String should have at least 1 character (given "   ")'
    article = {name: value for name, value in GOOD.items() if name != "resolution"}
    with pytest.raises(ValidationError, match="resolution\n  Field required"):
        Article.model_validate(article)


def test_each_field_has_a_most_characters():
    assert failure(title="x" * 201) == "title: String should have at most 200 characters"
    assert failure(system="y" * 101) == "system: String should have at most 100 characters"


def test_priority_is_one_of_four_values():
    assert failure(priority="Urgent") == \
        "priority: Input should be 'Low', 'Medium', 'High' or 'Critical' (given \"Urgent\")"
    assert [priority.value for priority in Priority] == ["Low", "Medium", "High", "Critical"]


def test_tags_are_split_in_lower_case_trimmed_and_each_kept_once():
    assert Article.model_validate({**GOOD, "tags": "VPN; vpn ;Remote  Access;;"}).tags == ["vpn", "remote access"]
    assert Article.model_validate({**GOOD, "tags": ""}).tags == []


def test_a_blank_optional_value_is_none_not_an_empty_label():
    article = Article.model_validate({**GOOD, "notes": " ", "system": "", "priority": ""})
    assert (article.notes, article.system, article.priority) == (None, None, None)


def test_visibility_is_one_of_three_in_lower_case():
    assert Article.model_validate({**GOOD, "visibility": " Internal "}).visibility == "internal"
    assert failure(visibility="secret") == \
        "visibility: Input should be 'public', 'internal' or 'restricted' (given \"secret\")"


def test_a_field_the_schema_doesnt_have_fails():
    assert failure(owner="Ana") == "owner: Extra inputs are not permitted (given \"Ana\")"


def test_a_long_value_isnt_shown_in_the_error_line():
    assert "given" not in failure(priority="U" * 41)


def test_an_article_cant_be_changed_once_checked():
    with pytest.raises(ValidationError, match="frozen"):
        Article.model_validate(GOOD).title = "Another"


# -------------------------------------------------
# Spellings
# -------------------------------------------------

def test_case_spaces_hyphens_and_underscores_never_count():
    systems = Spellings({"WiFi": [], "Active Directory": ["AD"]})
    assert [systems.right_spelling(value) for value in ("Wi-Fi", "WIFI", "wi fi", "wi_fi", "WiFi")] == ["WiFi"] * 5
    assert systems.right_spelling("active-directory") == "Active Directory"


def test_the_other_spellings_find_the_right_one():
    systems = Spellings({"Active Directory": ["AD"], "Microsoft Teams": ["Teams", "MS Teams"]})
    assert (systems.right_spelling("ad"), systems.right_spelling("ms-teams")) == ("Active Directory", "Microsoft Teams")


def test_a_spelling_the_table_doesnt_know_is_none():
    assert Spellings({"WiFi": []}).right_spelling("Kiosk") is None


# -------------------------------------------------
# doc_id()
# -------------------------------------------------

def test_an_id_is_kb_and_a_hash_of_the_title_and_system():
    the_id = doc_id(GOOD, ("title", "system"))
    assert the_id.startswith("kb-") and len(the_id) == 19
    assert int(the_id[3:], 16) >= 0                        # 16 hex digits


def test_an_id_ignores_case_and_spacing_and_the_other_fields():
    same = {**GOOD, "title": "  vpn   connection TIMEOUT ", "resolution": "Another fix", "priority": "Low"}
    assert doc_id(same, ("title", "system")) == doc_id(GOOD, ("title", "system"))
    assert doc_id({**GOOD, "system": "MFA"}, ("title", "system")) != doc_id(GOOD, ("title", "system"))


def test_the_exports_own_id_comes_first():
    assert doc_id({**GOOD, "id": "KB0012"}, ("title", "system")) == "KB0012"


def test_no_id_without_a_value_for_each_id_field():
    assert doc_id({**GOOD, "system": ""}, ("title", "system")) is None
