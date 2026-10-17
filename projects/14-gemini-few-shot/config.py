"""
Load the Gemini API key and check it before anything else runs. The same file as projects 9 to 13.

    load_api_key()  ->  the key, from the environment or from the .env file next to this one
                        no key (or still the placeholder)  ->  MissingKeyError with a message saying what to do

Run it on its own:   python config.py   ->   "GOOGLE_API_KEY is set." (the key itself is never printed)
hello.py calls load_api_key() before it builds the model, and stops without a key.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# The .env file next to this one. It's in .gitignore, so the real key never goes into git.
ENV_FILE = Path(__file__).with_name(".env")
PLACEHOLDER = "your-key-here"            # what .env.example says, before you put your real key in


class MissingKeyError(RuntimeError):
    """There's no usable GOOGLE_API_KEY. The message says how to set one."""


# ① Load: copy the lines of .env into the environment, then read the key from there.
#    load_dotenv() doesn't overwrite a variable that's already set, so a key set outside the file (a Codespaces
#    secret, or the hosting provider's settings in production) wins over the file.
def load_api_key(env_file: Path = ENV_FILE) -> str:
    load_dotenv(env_file)
    key = os.getenv("GOOGLE_API_KEY", "").strip()

    # ② Fail fast: stop now with a clear message, rather than later with a confusing error from the first model call.
    if not key:
        raise MissingKeyError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, "
            "or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret)."
        )
    if key == PLACEHOLDER:
        raise MissingKeyError("GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.")
    return key


if __name__ == "__main__":
    try:
        load_api_key()
    except MissingKeyError as err:
        sys.exit(str(err))                   # prints the message and exits with code 1: no stack trace
    print("GOOGLE_API_KEY is set.")          # never print the key itself, not even part of it
