"""
Prompts as files: one file per version, named <prompt>.v<number>.md, in the prompts/ folder.

    prompts/greeting.v1.md   prompts/greeting.v2.md   prompts/greeting.v3.md

Each file has a "## system" section and a "## human" section. Anything above them, such as a "# ..." line at the
top, is a note for people and is ignored. load_all("greeting", needs={"name"}) reads every version once, when the
program starts, and checks each one. prompt_versions.toml says which version is in use.

    load_all("greeting", needs={"name"})["v3"]
        ->  PromptVersion(name="greeting", version="v3", fingerprint="c27b3feb", ...)
    active_version("greeting")  ->  "v3"

The fingerprint is a short hash of the file's text. If anyone edits a file, its fingerprint changes, so an answer
can always be traced to the exact words that produced it. A broken file, or a broken prompt_versions.toml, raises
PromptFileError with a message that says what to fix.

hello.py imports it; it has nothing to run on its own. To try it, with no key and no call:
    python -c "from prompt_files import load_all; print(load_all('greeting', needs={'name'})['v3'].fingerprint)"
        ->  c27b3feb
"""
import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

FOLDER = Path(__file__).resolve().parent
PROMPTS = FOLDER / "prompts"
VERSIONS_FILE = FOLDER / "prompt_versions.toml"      # says which version of each prompt is in use


class PromptFileError(ValueError):
    """A prompt file or prompt_versions.toml is missing something, badly shaped, or uses the wrong {variables}."""


# One loaded version. @dataclass writes the __init__ (and a readable print-out) from the fields listed here, and
# frozen=True makes the object read-only, like a Java record: a loaded version can't be changed by accident.
@dataclass(frozen=True)
class PromptVersion:
    name: str            # "greeting"
    version: str         # "v3"
    system: str          # the system message, as written in the file
    human: str           # the human message, with its {name}
    fingerprint: str     # the first 8 characters of the file's SHA-256 hash
    template: ChatPromptTemplate


def fingerprint(text: str) -> str:
    """The first 8 characters of the text's SHA-256 hash: "c27b3feb" for prompts/greeting.v3.md."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


# ① Read one file: split it at the "## system" and "## human" headings.
def parse(path: Path, needs: set[str]) -> PromptVersion:
    name, version = path.name.removesuffix(".md").split(".", 1)        # "greeting.v3.md" -> "greeting", "v3"
    # read_text() reads Windows line endings (\r\n, which Git on Windows may check a file out with) as \n, the same
    # as on Linux. So the headings are found, and the fingerprint is the same, on both.
    text = path.read_text(encoding="utf-8")
    # re.split with a (group) in the pattern keeps the headings it splits at, so the file becomes a list:
    #   ["# greeting v2: ...\n\n", "system", "\nYou write short ...\n\n", "human", "\nWrite a welcome for {name} ...\n"]
    # Item 0 is the note for people (never sent); after it, each heading is followed by its text.
    parts = re.split(r"^## (system|human)[ \t]*$", text, flags=re.MULTILINE)
    headings, bodies = parts[1::2], parts[2::2]          # [1::2] is every second item, starting at item 1
    sections = {heading: body.strip() for heading, body in zip(headings, bodies)}
    # Exactly one of each: with two "## system" sections, the second would quietly replace the first.
    if sorted(headings) != ["human", "system"] or not all(sections.values()):
        raise PromptFileError(f"{path.name} needs a '## system' and a '## human' section, each with some text")

    try:
        template = ChatPromptTemplate.from_messages([("system", sections["system"]), ("human", sections["human"])])
    except ValueError as err:          # { and } mark a variable: "{name" without its }, or "{name.upper}", is refused
        raise PromptFileError(f"{path.name} has braces that don't make a variable: {err}") from err
    # Fail at start-up, not on the first request: the file must use exactly the variables the code fills in.
    if set(template.input_variables) != needs:
        raise PromptFileError(f"{path.name} uses {sorted(template.input_variables)}, but the code fills in {sorted(needs)}")
    return PromptVersion(name, version, sections["system"], sections["human"], fingerprint(text), template)


# ② Read every version of one prompt, in order: v1, v2, ... v10 (by number, not alphabetically).
def version_number(path: Path) -> int:
    """greeting.v10.md -> 10. Any other name, such as a copy called "greeting.v3 - Copy.md", is refused."""
    match = re.fullmatch(r"\w+\.v(\d+)\.md", path.name)
    if match is None:
        raise PromptFileError(f"{path.name} isn't named <prompt>.v<number>.md: rename it, or move it out of prompts/")
    return int(match.group(1))


def load_all(name: str, needs: set[str]) -> dict[str, PromptVersion]:
    paths = sorted(PROMPTS.glob(f"{name}.v*.md"), key=version_number)
    if not paths:
        raise PromptFileError(f"no prompt files for {name!r} in {PROMPTS}")
    versions = [parse(path, needs) for path in paths]
    return {prompt.version: prompt for prompt in versions}         # {"v1": PromptVersion(...), "v2": ..., ...}


# ③ Which version is in use: one line per prompt in prompt_versions.toml.
#    tomllib is Python's own TOML reader (Python 3.11 and later). It reads bytes, so the file is opened with "rb".
def active_version(name: str, path: Path = VERSIONS_FILE) -> str:
    with path.open("rb") as file:
        try:
            settings = tomllib.load(file)                # greeting = "v3"  ->  {"greeting": "v3"}
        except tomllib.TOMLDecodeError as err:
            raise PromptFileError(f"{path.name} isn't valid TOML ({err}): write it as {name} = \"v3\"") from err
    if name not in settings:
        raise PromptFileError(f"{path.name} doesn't say which {name} version to use: add a line {name} = \"v3\"")
    return settings[name]
