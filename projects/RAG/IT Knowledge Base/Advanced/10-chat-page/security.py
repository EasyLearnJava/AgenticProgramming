"""
IT Knowledge Base: Who Gets In, and How Often
=============================================

Guards the API's door. It handles:
  1. API keys: each caller has a name and a key, and only the key's SHA-256 hash is kept (in the keys file), so the
     file can't be used to call the API, and no key is ever stored or logged; a key is checked against every hash in
     constant time
  2. add_key(): a new random key for a caller, its hash written to the keys file; the key is shown once, so only its
     holder has it
  3. RateLimiter: each caller's requests a minute, as a token bucket: up to `per_minute` at once, then one more every
     60 / per_minute seconds; a request over the limit is told how long to wait

    keys = ApiKeys.load(Path("data/api_keys.toml"))
    keys.caller("kb_...")  ->  "chat-page"   (None for a key no caller has)
"""
import hashlib
import hmac
import re
import secrets
import threading
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

# The defaults: kb_settings.toml's [api] can change each one
REQUESTS_PER_MINUTE = 30
MAX_BODY_BYTES = 16_384

KEY_PREFIX = "kb_"                                   # a key starts with this, so a leaked one is easy to spot
NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")          # a caller's name: also a bare key in the keys file
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KeysError(RuntimeError):
    """The keys file can't be read or written, or a caller's name isn't valid; the message says why."""


def key_hash(key: str) -> str:
    """What the keys file keeps of a key: its SHA-256, in hex. A key is 256 random bits, so the hash can't be
    reversed or guessed."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


# -------------------------------------------------
# ApiKeys Class - The Callers Allowed In
# -------------------------------------------------

class ApiKeys:
    """The callers allowed in: each name with its key's hash."""

    def __init__(self, hashes: dict[str, str]):
        self.hashes = dict(hashes)

    @classmethod
    def load(cls, path: Path) -> "ApiKeys":
        """The keys file's callers, one `name = "<SHA-256 of its key>"` line each; no file, no callers.

        Raises:
            KeysError: the file can't be read, or a line isn't a name and a hash
        """
        path = Path(path)
        if not path.is_file():
            return cls({})
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
            raise KeysError(f"The keys file can't be read ({err}): {path.resolve()}") from None
        bad = [name for name, value in data.items()
               if not NAME.match(name) or not isinstance(value, str) or not SHA256.match(value)]
        if bad:
            raise KeysError(f"The keys file has a bad line for {', '.join(bad)}: each is name = \"<its key's SHA-256, "
                            f"64 hex digits>\" (python main.py add-key NAME writes one): {path.resolve()}")
        return cls(data)

    def caller(self, key: str) -> str | None:
        """The name of the caller whose key this is; None when no caller has it. Every hash is compared, each in
        constant time, so how long it takes says nothing about the keys."""
        given = key_hash(key)
        found = None
        for name, stored in self.hashes.items():
            if hmac.compare_digest(given, stored):
                found = name
        return found

    def __len__(self) -> int:
        return len(self.hashes)


def add_key(path: Path, name: str) -> str:
    """
    A new key for the caller `name`, its hash written to the keys file (the caller's old key, if it had one, stops
    working). Returns the key: it's kept nowhere, so it's shown once.

    Raises:
        KeysError: the name isn't valid, or the file can't be read or written
    """
    if not NAME.match(name):
        raise KeysError(f"A caller's name is 1 to 40 letters, digits, - or _, not {name!r}")
    path = Path(path)
    keys = ApiKeys.load(path)
    key = new_key()
    keys.hashes[name] = key_hash(key)
    lines = ["# Each caller's name and its API key's SHA-256: python main.py add-key NAME adds one, or a new key",
             *(f'{caller} = "{digest}"' for caller, digest in sorted(keys.hashes.items()))]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as err:
        raise KeysError(f"The keys file can't be written ({err}): {path.resolve()}") from None
    return key


# -------------------------------------------------
# RateLimiter Class - Each Caller's Requests a Minute
# -------------------------------------------------

class RateLimiter:
    """
    A token bucket per caller: a caller starts with `per_minute` tokens, each request takes one, and one comes back
    every 60 / per_minute seconds, up to `per_minute`. The counts are this process's: several servers would each allow
    as many (a store they share, such as Redis, would count for all of them).
    """

    def __init__(self, per_minute: int = REQUESTS_PER_MINUTE, *, clock: Callable[[], float] = time.monotonic):
        self.per_minute = per_minute
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}     # caller -> (tokens, when they were counted)
        self._lock = threading.Lock()

    def take(self, caller: str) -> float:
        """Take one of the caller's tokens: 0.0 when there was one (the request goes ahead), else the seconds until
        there is."""
        per_second = self.per_minute / 60
        with self._lock:
            now = self.clock()
            tokens, counted = self._buckets.get(caller, (float(self.per_minute), now))
            tokens = min(float(self.per_minute), tokens + (now - counted) * per_second)
            if tokens >= 1:
                self._buckets[caller] = (tokens - 1, now)
                return 0.0
            self._buckets[caller] = (tokens, now)
            return (1 - tokens) / per_second
