"""
Tests for security.py: a key is found by its hash and only its hash is kept; the keys file is read, checked and
written; a new key replaces a caller's old one; and the rate limiter lets a burst through, then one request every
60 / per_minute seconds, each caller on its own.
"""
import pytest

from security import KEY_PREFIX, ApiKeys, KeysError, RateLimiter, add_key, key_hash, new_key


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_new_key_is_long_random_and_easy_to_spot():
    first, second = new_key(), new_key()
    assert first.startswith(KEY_PREFIX) and len(first) == len(KEY_PREFIX) + 43 and first != second
    assert key_hash(first) == key_hash(first) and len(key_hash(first)) == 64


def test_a_key_is_found_by_its_hash():
    keys = ApiKeys({"chat-page": key_hash("kb_one"), "reports": key_hash("kb_two")})
    assert (keys.caller("kb_one"), keys.caller("kb_two"), keys.caller("kb_three"), len(keys)) == (
        "chat-page", "reports", None, 2)


def test_added_keys_are_kept_only_as_hashes_and_a_new_one_replaces_the_old(tmp_path):
    path = tmp_path / "data" / "api_keys.toml"
    first = add_key(path, "chat-page")
    add_key(path, "reports")
    second = add_key(path, "chat-page")
    text = path.read_text(encoding="utf-8")
    assert first not in text and second not in text and key_hash(second) in text
    keys = ApiKeys.load(path)
    assert (keys.caller(second), keys.caller(first), len(keys)) == ("chat-page", None, 2)


def test_no_keys_file_means_no_callers(tmp_path):
    assert len(ApiKeys.load(tmp_path / "missing.toml")) == 0


@pytest.mark.parametrize("content, problem", [
    ('chat-page = "not-a-hash"\n', "a bad line for chat-page"),
    ('chat-page = 12\n', "a bad line for chat-page"),
    ('chat page = "x"\n', "can't be read"),
], ids=["not a hash", "not text", "not TOML"])
def test_a_bad_keys_file_is_named(tmp_path, content, problem):
    path = tmp_path / "api_keys.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(KeysError, match=problem):
        ApiKeys.load(path)


def test_a_callers_name_must_be_simple(tmp_path):
    with pytest.raises(KeysError, match="1 to 40 letters"):
        add_key(tmp_path / "api_keys.toml", "chat page")


def test_the_limiter_lets_a_burst_through_then_one_every_few_seconds():
    clock = Clock()
    limiter = RateLimiter(per_minute=3, clock=clock)
    assert [limiter.take("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.take("a") == pytest.approx(20.0)          # one token every 60 / 3 seconds
    assert limiter.take("b") == 0.0                          # each caller has its own bucket
    clock.now += 10
    assert limiter.take("a") == pytest.approx(10.0)
    clock.now += 10
    assert limiter.take("a") == 0.0 and limiter.take("a") > 0
    clock.now += 600                                         # a long wait refills it, but only to the burst
    assert [limiter.take("a") == 0.0 for _ in range(4)] == [True, True, True, False]
