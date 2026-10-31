"""
IT Knowledge Base: The Gemini API Key
=====================================

Loads the Gemini API key and checks it before anything is sent anywhere. It handles:
  1. Reading GOOGLE_API_KEY from the environment, or from the .env file next to this one
  2. Stopping with a clear MissingKeyError when there's no usable key
  3. Handing the key over as a secret value (pydantic's SecretStr): printed or logged, it shows as **********

Usage (pipeline.py calls it when kb_settings.toml's embedding provider is "google"):
    load_api_key()   ->  SecretStr; or MissingKeyError, saying how to set one (the key itself is never printed)
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr

# .env is in .gitignore, so the real key never goes into git
ENV_FILE = Path(__file__).with_name(".env")
PLACEHOLDER = "your-key-here"            # what .env.example says, before you put your real key in


class MissingKeyError(RuntimeError):
    """There's no usable GOOGLE_API_KEY. The message says how to set one."""


def load_api_key(env_file: Path = ENV_FILE) -> SecretStr:
    """The key, from the environment or the .env file; MissingKeyError if it's missing or still the placeholder."""
    # load_dotenv() doesn't overwrite a variable that's already set, so a key set outside the file wins
    try:
        load_dotenv(env_file)
    except UnicodeDecodeError:
        # PowerShell 5's `echo ... > .env` saves the file as UTF-16, which can't be read
        raise MissingKeyError(
            f"{env_file.name} isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding."
        ) from None
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    # Fail fast, with a clear message, rather than later with a confusing error from the first call
    if not key:
        raise MissingKeyError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set "
            "GOOGLE_API_KEY as an environment variable; or, to run without a key, set provider = \"fake\" in "
            "kb_settings.toml's [embeddings].")
    if key == PLACEHOLDER:
        raise MissingKeyError("GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.")
    return SecretStr(key)
