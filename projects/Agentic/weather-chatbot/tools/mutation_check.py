"""
tools/mutation_check.py: proves the unit tests guard the app's rules. Each mutation breaks one rule in the code, the
way a bug would; the unit tests must fail with it. Every file is put back as it was, whatever happens. Run it from the
project's folder: `uv run python tools/mutation_check.py`.
"""

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Mutation(NamedTuple):
    """One rule broken: in which file, the text replaced and its replacement, and the rule's name."""

    file: str
    old: str
    new: str
    rule: str


MUTATIONS = (
    Mutation("nimbus/constants.py", r'r"[\w:.-]{1,128}", re.ASCII', r'r"[\w:.-]{1,128}"', "a request id is ASCII"),
    Mutation("nimbus/constants.py", "{1,128}", "{1,129}", "a request id is at most 128 characters"),
    Mutation("nimbus/docs.py", '{"html": False}', '{"html": True}', "the docs never render raw HTML"),
    Mutation(
        "nimbus/docs.py",
        "return DOC_BY_PATH.get(path)",
        "return ALL_DOCS.get(path.rsplit('/', 1)[-1])",
        "a page is found by its own address",
    ),
    Mutation("nimbus/docs.py", 'return f"/docs/{src}" if', "return src if", "a picture's address is the app's"),
    Mutation("nimbus/docs.py", 'del tokens[idx].attrs["style"]', "pass", "an aligned column has no inline style"),
    Mutation("nimbus/pages.py", 'if href != "/" and path.startswith', "if path.startswith", "Chat isn't a section"),
    Mutation("nimbus/pages.py", 'Markup("<wbr>_deprecated")', '"_deprecated"', "a label may break before _deprecated"),
    Mutation(
        "nimbus/middleware.py",
        '"path": scope["path"],',
        '"path": scope["path"] + "?" + scope["query_string"].decode(),',
        "the query string is never logged",
    ),
    Mutation(
        "nimbus/middleware.py",
        "for name, value in SECURITY_HEADERS:",
        "for name, value in SECURITY_HEADERS[1:]:",
        "every response has the Content Security Policy",
    ),
    Mutation(
        "nimbus/middleware.py",
        "MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)",
        "pass",
        "the request id goes back to the browser",
    ),
    Mutation("nimbus/config.py", "env_ignore_empty=True", "env_ignore_empty=False", "an empty setting is unset"),
    Mutation(
        "nimbus/config.py",
        "WithoutVercelFields(settings_cls, dotenv_settings)",
        "dotenv_settings",
        "Vercel's own settings never come from a .env file",
    ),
    Mutation("nimbus/utils.py", '.replace("+00:00", "Z")', "", "a time is written with Z"),
    Mutation("nimbus/app.py", "if not settings.is_vercel:", "if True:", "on Vercel, public/ is never mounted"),
    Mutation("nimbus/health.py", 'methods=["GET", "HEAD"]', 'methods=["GET"]', "the health check answers HEAD"),
)


def is_caught(mutation: Mutation) -> bool:
    """Whether the unit tests fail with this mutation in place; the file is put back afterwards."""
    path = PROJECT_ROOT / mutation.file
    original = path.read_text(encoding="utf-8")
    if original.count(mutation.old) != 1:
        raise RuntimeError(f"{mutation.file} doesn't hold this text exactly once: {mutation.old!r}")
    try:
        path.write_text(original.replace(mutation.old, mutation.new, 1), encoding="utf-8", newline="\n")
        # The unit tests, with this same Python: `uv run` started it in the project's environment.
        tests = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
        )
        return tests.returncode != 0
    finally:
        path.write_text(original, encoding="utf-8", newline="\n")


def main() -> int:
    """Runs every mutation and says which the tests caught; 1 if any wasn't."""
    missed = 0
    for mutation in MUTATIONS:
        caught = is_caught(mutation)
        missed += not caught
        print(f"{'caught' if caught else 'MISSED'}: {mutation.rule}")
    print(f"{len(MUTATIONS) - missed} of {len(MUTATIONS)} caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
