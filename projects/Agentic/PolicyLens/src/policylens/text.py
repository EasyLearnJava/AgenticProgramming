"""Unicode text, grammatical normalization and shared retrieval features."""

import re
import threading
import unicodedata
from functools import lru_cache

import snowballstemmer

# Grammatical stop words, not a list of corpus-specific policy vocabulary.
STOP_WORDS = set("""a an the and or but if of to in on at for from with by is are was were be
been being do does did can could would should will may might must i me my we our you your
it its this that these those what which who how when where why tell about please explain
have has had as not there than then also all their them they he she his her any some each
through between within during into across much many such so just now here very more most
before after up down out only own same other another both either neither this that""".split())
PUNCTUATION = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"',
                           "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"})
_local = threading.local()


def canonical_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(PUNCTUATION).casefold()


def normalize(text: str) -> str:
    return " ".join(re.sub(r"\s*-\s*", "-", canonical_text(text)).split())


def expand_contractions(text: str) -> str:
    text = canonical_text(text)
    for short, full in {"can't": "can not", "won't": "will not", "shan't": "shall not",
                        "cannot": "can not", "what's": "what is", "it's": "it is"}.items():
        text = re.sub(r"\b" + re.escape(short) + r"\b", full, text)
    text = re.sub(r"\b([^\W_]+)n't\b", r"\1 not", text)
    return re.sub(r"\b([^\W_]+)'s\b", r"\1", text)


@lru_cache(maxsize=30000)
def stem(word: str) -> str:
    # Snowball's Python stemmer is mutable: never share one across worker threads.
    if not hasattr(_local, "english"):
        _local.english = snowballstemmer.stemmer("english")
    return _local.english.stemWord(word) if word.isascii() and word.isalpha() else word


def tokens(text: str) -> list[str]:
    """Preserve Unicode, split hyphens, stem English, and retain exact code tokens.

    CJK character bigrams provide a useful lexical fallback without pretending to
    be a language-specific segmenter or semantic embedding model.
    """
    result = []
    for word in re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", expand_contractions(text)):
        parts = word.split("-")
        if len(parts) > 1:
            result.append(word)  # SEC-101 still has an exact-match feature.
        for part in parts:
            if part in STOP_WORDS or len(part) < 2:
                continue
            result.append(stem(part))
            if re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", part):
                result.extend(part[i:i + 2] for i in range(len(part) - 1))
    return result


def clean_text(text: str) -> str:
    # HTML decoding belongs to the HTML fetcher; uploads may contain literal URLs/entities.
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text)
            if 15 <= len(part.strip()) <= 850 and not part.strip().startswith("#")]

