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
    # Step 2: the chat.
    Mutation(
        "nimbus/constants.py",
        "QUESTION_MAX_CHARS: Final = 2000",
        "QUESTION_MAX_CHARS: Final = 2001",
        "a question is at most 2,000 characters",
    ),
    Mutation(
        "nimbus/constants.py",
        "CHAT_BODY_MAX_BYTES: Final = 32 * 1024",
        "CHAT_BODY_MAX_BYTES: Final = 64 * 1024",
        "a body over 32 KiB is refused",
    ),
    Mutation(
        "nimbus/chat.py",
        "if declared.isascii() and declared.isdecimal() and int(declared) > max_bytes:",
        "if False:",
        "a body too large is refused from its declared length alone",
    ),
    Mutation("nimbus/chat.py", "if size > max_bytes:", "if False:", "a body too large is refused as it's read"),
    Mutation(
        "nimbus/chat.py",
        'if any(field != "question" for field, _ in problems):',
        "if False:",
        "a form with a field the chat doesn't know can't be read",
    ),
    Mutation(
        "nimbus/chat.py",
        "return Response(status_code=HTTP_CLIENT_CLOSED_REQUEST)",
        "raise",
        "a browser gone while sending its question isn't an error",
    ),
    Mutation("nimbus/chat.py", "first = await anext(turn)", 'first = ""', "an answer starts before its response"),
    Mutation("nimbus/chat.py", "if len(fields) != len(pairs):", "if False:", "each field of the form comes once"),
    Mutation("nimbus/chat.py", 'extra="forbid"', 'extra="ignore"', "a field the chat doesn't know is refused"),
    Mutation(
        "nimbus/chat.py",
        'log.info("chat.request", questionChars=len(chat_request.question), **extra)',
        'log.info("chat.request", questionChars=len(chat_request.question), question=chat_request.question, **extra)',
        "a question is never logged",
    ),
    Mutation(
        "nimbus/chat.py",
        "except (asyncio.CancelledError, GeneratorExit):",
        "except asyncio.CancelledError:",
        "Stop is logged however the server reports it",
    ),
    Mutation("nimbus/chat.py", "await self.source.aclose()", "pass", "an answer's end is logged within its request"),
    Mutation(
        "nimbus/chat.py",
        "with suppress(ClientDisconnect):",
        "with suppress():",
        "a browser that has gone isn't an error",
    ),
    Mutation(
        "nimbus/chat.py",
        'note = f"{to_user_message(error)} (ref {to_ref(request_id)})"',
        'note = f"{error} (ref {to_ref(request_id)})"',
        "a failure never shows its own text",
    ),
    Mutation(
        "nimbus/chat.py",
        'super().__init__(self.events, headers={"cache-control": NO_STORE})',
        "super().__init__(self.events)",
        "an answer's stream is never cached",
    ),
    Mutation("nimbus/chat.py", 'headers={ERROR_HEADER: "1"}', "headers={}", "our own error pages are marked as ours"),
    Mutation("nimbus/errors.py", "else UNEXPECTED", "else str(error)", "any other error gets the fixed sentence"),
    Mutation(
        "nimbus/utils.py",
        r'SSE_LINE_BREAK = re.compile(r"\r\n|\r|\n")',
        r'SSE_LINE_BREAK = re.compile(r"\n")',
        "an event's lines break where the browser's do",
    ),
    Mutation("nimbus/utils.py", "[-REF_CHARS:]", "[:REF_CHARS]", "a ref is the end of the request's id"),
    Mutation(
        "nimbus/middleware.py",
        'scope.setdefault("state", {})["request_id"] = request_id',
        "pass",
        "the app finds the request's id in its state",
    ),
    Mutation("templates/chat.html", 'hx-sync="this:drop"', "", "Enter while an answer streams sends nothing more"),
    Mutation(
        "templates/chat.html",
        'method="post" action="/api/chat" ',
        "",
        "without htmx, a question never goes into the address",
    ),
    # Step 3: Gemini.
    Mutation(
        "nimbus/constants.py",
        "MAX_OUTPUT_TOKENS: Final = 1024",
        "MAX_OUTPUT_TOKENS: Final = 8192",
        "an answer is at most 1,024 tokens",
    ),
    Mutation(
        "nimbus/constants.py",
        "ANSWER_TIMEOUT_SECONDS: Final = 30",
        "ANSWER_TIMEOUT_SECONDS: Final = 300",
        "an answer stops at 30 seconds",
    ),
    Mutation(
        "nimbus/constants.py",
        "MODEL_MAX_ATTEMPTS: Final = 2",
        "MODEL_MAX_ATTEMPTS: Final = 6",
        "a failed call to Gemini is tried once more, not five times",
    ),
    Mutation(
        "nimbus/constants.py",
        'MODEL_THINKING: Final = "minimal"',
        'MODEL_THINKING: Final = "high"',
        "the least thinking",
    ),
    Mutation(
        "nimbus/model.py",
        "hide_inputs=True, hide_outputs=True",
        "hide_inputs=None, hide_outputs=None",
        "the tracer hides inputs and outputs, whatever LangSmith's variables say",
    ),
    Mutation(
        "nimbus/model.py",
        "project=settings.langsmith_project",
        "project=None",
        "the tracer's project is the app's setting",
    ),
    Mutation(
        "nimbus/answer.py",
        "client=client, project_name=project",
        "client=client, project_name=None",
        "the run is traced into the tracer's project",
    ),
    Mutation(
        "nimbus/model.py",
        "        and settings.langsmith_hide_outputs\n",
        "",
        "LangSmith traces only when it hides both inputs and outputs",
    ),
    Mutation(
        "nimbus/answer.py",
        "raise ModelBusyError from error",
        "raise ModelFailedError from error",
        "a model's rate limit says the assistant is busy",
    ),
    Mutation(
        "nimbus/answer.py",
        "raise ConfigError from error",
        "raise ModelFailedError from error",
        "a key the model refuses says the assistant isn't set up",
    ),
    Mutation(
        "nimbus/answer.py",
        "raise ModelFailedError from error",
        "raise ModelFailedError from None",
        "a model's own error is kept as the cause",
    ),
    Mutation(
        "nimbus/answer.py",
        "ModelPermissionDeniedError, ModelNotFoundError)):",
        "ModelPermissionDeniedError)):",
        "a model name the provider doesn't know says the assistant isn't set up",
    ),
    Mutation(
        "nimbus/answer.py",
        'return isinstance(error, ModelInvalidRequestError) and BAD_KEY_REASON in f"{error} {error.__cause__}"',
        "return False",
        "Gemini's 400 for a bad key says the assistant isn't set up",
    ),
    Mutation(
        "nimbus/answer.py",
        "stats.tokens_out += chunk.usage_metadata",
        "stats.tokens_out = chunk.usage_metadata",
        "each chunk's tokens add up",
    ),
    Mutation("nimbus/answer.py", '.disable("image")', "", "an answer never loads a picture"),
    Mutation(
        "nimbus/answer.py",
        'tokens[idx].attrSet("rel", LINK_REL)',
        "pass",
        "an answer's link tells the other site nothing",
    ),
    Mutation(
        "nimbus/prompts.py",
        "local = now.astimezone(ZoneInfo(time_zone))",
        "local = now",
        "today and tomorrow are the visitor's own",
    ),
    Mutation(
        "nimbus/prompts.py",
        "return IMPERIAL if to_region(locale) in IMPERIAL_REGIONS else METRIC",
        "return METRIC",
        "the units follow the locale",
    ),
    Mutation(
        "nimbus/prompts.py",
        "if len(subtag) == 1:\n            break",
        "if len(subtag) == 1:\n            pass",
        "a locale's region comes before any extension",
    ),
    Mutation(
        "nimbus/chat.py",
        "isinstance(value, str) and value in TIME_ZONES",
        "isinstance(value, str)",
        "a time zone must be a known one",
    ),
    Mutation(
        "nimbus/chat.py",
        "return value if usable else DEFAULT_LOCALE",
        "return value",
        "a locale the chat can't use takes the default",
    ),
    Mutation("nimbus/chat.py", "if model is None:", "if False:", "a deployment without a key says it isn't set up"),
    Mutation(
        "nimbus/chat.py",
        'html = render_answer("".join(pieces))',
        'html = "".join(pieces)',
        "the finished answer's Markdown is HTML",
    ),
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
