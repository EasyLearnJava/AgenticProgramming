"""
nimbus/constants.py: the app's fixed values: where its files are, the headers it reads and sends, the security headers
on every response, the chat's limits, and the model's caps. One place for each value, so the code and its tests always
agree.
"""

import logging
import re
from pathlib import Path
from typing import Final

# ① Where the app's files are, found from this file's place in the project, since the working directory can be
# anywhere: Vercel runs the app from the project's root, a test may run from elsewhere.
PROJECT_ROOT: Final = Path(__file__).resolve().parent.parent
DOCS_DIR: Final = PROJECT_ROOT / "docs"
DOCS_IMAGES_DIR: Final = DOCS_DIR / "images"
TEMPLATES_DIR: Final = PROJECT_ROOT / "templates"
# The stylesheet: Vercel's CDN serves public/ itself, so on Vercel the function never has this folder.
STATIC_DIR: Final = PROJECT_ROOT / "public" / "static"

# ② The request id: Vercel's own id for the request, when it looks like one, else a new one. Every log line carries
# it, and the browser gets it back in a header. ASCII only: Python's \w would also take any Unicode letter.
VERCEL_ID_HEADER: Final = "x-vercel-id"
REQUEST_ID_HEADER: Final = "x-request-id"
REQUEST_ID_PATTERN: Final = re.compile(r"[\w:.-]{1,128}", re.ASCII)
NEW_REQUEST_ID_CHARS: Final = 16

# ③ The security headers on every response the app makes; vercel.json gives the CDN's files the same ones. The
# Content Security Policy is enforced from the start: the pages load only our own stylesheet, scripts and pictures,
# and no other site may show them in a frame.
CONTENT_SECURITY_POLICY: Final = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
)
SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("content-security-policy", CONTENT_SECURITY_POLICY),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("x-frame-options", "DENY"),
    ("permissions-policy", "camera=(), geolocation=(self), microphone=()"),
)

# ④ The health check's answer is never cached: it says how the app is now; nor is an answer's stream.
NO_STORE: Final = "no-store"

# ⑤ The chat (step 2): what the form sends, and what comes back. A question is at most 2,000 characters; the body
# that carries it, at most 32 KiB, room for 2,000 characters of four UTF-8 bytes each, written %XX. The answer streams
# as server-sent events; our own error pages carry a header, so the page can tell them from anyone else's.
FORM_MEDIA_TYPE: Final = "application/x-www-form-urlencoded"
QUESTION_MAX_CHARS: Final = 2000
CHAT_BODY_MAX_BYTES: Final = 32 * 1024
CHAT_FORM_MAX_FIELDS: Final = 10
EVENT_STREAM: Final = "text/event-stream"
ERROR_HEADER: Final = "x-nimbus-error"

# ⑥ The visitor's locale and time zone, which the page sends with each question (step 3): a language tag such as
# "en-US", and a time zone of the IANA database such as "America/Chicago". Without them, the defaults.
DEFAULT_LOCALE: Final = "en-US"
DEFAULT_TIME_ZONE: Final = "UTC"
# A language tag: a language, then subtags of letters and digits (a script, a region, extensions such as -u-ca-...).
# Letters, digits and hyphens only, so nothing in it can read as an instruction in the system prompt.
LOCALE_PATTERN: Final = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*", re.ASCII)
LOCALE_MAX_CHARS: Final = 35
# Where the units are imperial, by the locale's region: the United States, Liberia and Myanmar.
IMPERIAL_REGIONS: Final = frozenset({"US", "LR", "MM"})

# ⑦ The model (step 3): Gemini, through LangChain, capped. On Vercel, Stop never reaches the function (issue 32), so
# an answer no one reads still runs to its end: each answer is at most 1,024 tokens and 30 seconds, whatever happens;
# each call to Gemini waits at most 20 s, and a failed one is tried once more. For Gemini, LangChain's max_retries
# counts every attempt, the first one included (google-genai's HttpRetryOptions.attempts): two attempts, one retry
# (issue 36). Its thinking stays at the least there is, since thinking's tokens count against the 1,024.
GEMINI_MODEL: Final = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS: Final = 1024
ANSWER_TIMEOUT_SECONDS: Final = 30
MODEL_REQUEST_TIMEOUT_SECONDS: Final = 20
MODEL_MAX_ATTEMPTS: Final = 2
MODEL_THINKING: Final = "minimal"

# ⑧ Other libraries' own log lines (httpx's, google-genai's, LangSmith's): only their warnings and worse are written,
# as lines of ours. Their info lines name each request they send, a query string included (issue 43). Of an
# exception, its class and its innermost 8 frames.
LIBRARY_LOG_LEVEL: Final = logging.WARNING
LIBRARY_LOG_MAX_FRAMES: Final = 8
