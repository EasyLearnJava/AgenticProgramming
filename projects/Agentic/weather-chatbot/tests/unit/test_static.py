"""
tests/unit/test_static.py: the scripts Vercel's CDN serves for the chat: htmx and its stream extension, exactly as npm
published version 4.0.0, and our own script, which puts text into the page and never HTML or code.
"""

import hashlib

import pytest

from nimbus.constants import STATIC_DIR

# The two files of npm's htmx.org 4.0.0 (dist/htmx.min.js and dist/ext/hx-sse.min.js), whose tarball matched the
# registry's integrity hash when they were copied.
HTMX_4_0_0 = {
    "htmx.min.js": "e484d9171a9db30a39c8f16e3d709d4137f3211c659f8e6125816635033d593f",
    "hx-sse.min.js": "8a834680c4000a9034d79228872372a92e140c810a075cb6d4a76690dfc13085",
}


@pytest.mark.parametrize(("name", "sha256"), HTMX_4_0_0.items())
def test_htmx_is_npm_s_own_file_unchanged(name: str, sha256: str) -> None:
    assert hashlib.sha256((STATIC_DIR / name).read_bytes()).hexdigest() == sha256


def test_our_script_puts_only_text_into_the_page_and_runs_no_text_as_code() -> None:
    script = (STATIC_DIR / "chat.js").read_text(encoding="utf-8")
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function("):
        assert unsafe not in script
    assert "textContent" in script
