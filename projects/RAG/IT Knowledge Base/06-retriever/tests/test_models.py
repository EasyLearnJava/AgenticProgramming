"""
Tests for models.py: the embedding model's name and size, and that every script stops with a clear message when there
is no key. The live test calls the real Gemini once.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import models

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
SCRIPTS = [name for name in ("similarity.py", "vector_store.py", "retriever.py", "rag_chain.py", "rag_engine.py",
                             "tuning.py") if (FOLDER / name).exists()]


def test_the_embedding_model_and_its_vector_size():
    assert models.embeddings.model == models.EMBEDDING_MODEL == "gemini-embedding-001"
    assert models.embeddings.output_dimensionality == models.EMBEDDING_SIZE == 768


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
    assert len(models.embeddings.embed_query("My VPN won't connect")) == 768
