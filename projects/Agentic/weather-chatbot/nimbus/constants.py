"""
nimbus/constants.py: the app's fixed values: where its files are, the headers it reads and sends, the security headers
on every response, and the chat's limits. One place for each value, so the code and its tests always agree.
"""

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
