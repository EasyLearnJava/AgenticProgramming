"""
Shared test set-up for this folder. pytest reads a file named conftest.py by itself, before any test file, so this
code runs first and decides once whether the live tests can run:

    a real key (in .env or the environment)  ->  every test runs, the @pytest.mark.live ones too (real Gemini calls)
    no key                                   ->  hello.py gets a fake key so it can be imported; live tests are skipped
"""
import os

import pytest

from config import MissingKeyError, load_api_key

try:
    load_api_key()                                         # a real key, in .env or the environment
    HAVE_KEY = True
except MissingKeyError:
    # No key: give hello.py a fake one so it can build the model. The plain tests never call Gemini.
    os.environ["GOOGLE_API_KEY"] = "fake-key-for-tests"
    HAVE_KEY = False


# A pytest "hook": pytest itself calls a function with exactly this name, after it has collected the tests and
# before it runs them. Nothing in our code calls it.
def pytest_collection_modifyitems(items):
    """Skip every @pytest.mark.live test when there is no real key."""
    if HAVE_KEY:
        return
    skip = pytest.mark.skip(reason="live test: needs GOOGLE_API_KEY (see project 9)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
