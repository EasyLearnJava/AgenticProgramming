"""tests/unit/test_errors.py: the app's own errors: each tells the visitor its own sentence; any other, a fixed one."""

from nimbus.errors import (
    CUT_OFF,
    EMPTY_QUESTION,
    STOPPED,
    UNEXPECTED,
    UNREACHABLE,
    InputError,
    NimbusError,
    to_user_message,
)


def test_an_error_the_app_expects_tells_the_visitor_its_own_sentence() -> None:
    error = InputError("question_empty", EMPTY_QUESTION)
    assert isinstance(error, NimbusError)
    assert error.status_code == 400
    assert error.code == "question_empty"
    assert to_user_message(error) == EMPTY_QUESTION


def test_an_input_error_may_have_its_own_status() -> None:
    assert InputError("not_a_form", EMPTY_QUESTION, 415).status_code == 415


def test_any_other_error_gets_a_fixed_sentence_never_its_own_text() -> None:
    assert to_user_message(RuntimeError("a secret detail")) == UNEXPECTED


def test_the_sentences_the_page_shows_by_itself_are_whole_sentences() -> None:
    for sentence in (STOPPED, CUT_OFF, UNREACHABLE, UNEXPECTED):
        assert sentence[0].isupper()
        assert sentence.endswith(".")
