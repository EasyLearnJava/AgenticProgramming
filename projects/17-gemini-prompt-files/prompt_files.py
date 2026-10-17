"""
Prompts as files: one file per version, named <prompt>.<version>.md, in the prompts/ folder.

    prompts/greeting.v1.md   prompts/greeting.v2.md   prompts/greeting.v3.md

Each file has a "## system" section and a "## human" section; a "# ..." line at the top is a note for people and
is ignored. load_all("greeting") reads every version once, when the server starts, and checks each one.

    load_all("greeting")["v3"]  ->  PromptVersion(name="greeting", version="v3", fingerprint="1a2b3c4d", ...)

The fingerprint is a short hash of the file's text. If anyone edits a file, its fingerprint changes, so an answer
can always be traced to the exact words that produced it.
"""
import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

FOLDER = Path(__file__).resolve().parent
PROMPTS = FOLDER / "prompts"
ACTIVE = FOLDER / "prompt_versions.toml"


class PromptFileError(ValueError):
    """A prompt file is missing, badly shaped, or uses the wrong {variables}."""


@dataclass(frozen=True)
class PromptVersion:
    name: str            # "greeting"
    version: str         # "v3"
    system: str          # the system message, as written in the file
    human: str           # the human message, with its {name}
    fingerprint: str     # the first 8 characters of the file's SHA-256 hash
    template: ChatPromptTemplate


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


# ① Read one file: split it at the "## system" and "## human" headings.
def parse(path: Path, needs: set[str]) -> PromptVersion:
    name, version = path.name.removesuffix(".md").split(".", 1)
    # Line endings are made the same first: Git on Windows may check a file out with \r\n, Linux with \n. So the
    # headings are found, and the fingerprint is the same, on both.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    parts = re.split(r"^## (system|human)[ \t]*$", text, flags=re.MULTILINE)
    sections = dict(zip(parts[1::2], (body.strip() for body in parts[2::2])))
    if set(sections) != {"system", "human"} or not all(sections.values()):
        raise PromptFileError(f"{path.name} needs a '## system' and a '## human' section, each with some text")

    template = ChatPromptTemplate.from_messages([("system", sections["system"]), ("human", sections["human"])])
    # Fail at start-up, not on the first request: the file must use exactly the variables the code fills in.
    if set(template.input_variables) != needs:
        raise PromptFileError(f"{path.name} uses {sorted(template.input_variables)}, but the code fills in {sorted(needs)}")
    return PromptVersion(name, version, sections["system"], sections["human"], fingerprint(text), template)


# ② Read every version of one prompt, in order: v1, v2, ... v10 (by number, not alphabetically).
def load_all(name: str, needs: set[str]) -> dict[str, PromptVersion]:
    paths = sorted(PROMPTS.glob(f"{name}.v*.md"), key=lambda p: int(p.name.split(".v")[1].split(".")[0]))
    if not paths:
        raise PromptFileError(f"no prompt files for {name!r} in {PROMPTS}")
    return {p.version: p for p in (parse(path, needs) for path in paths)}


# ③ Which version is in use: one line per prompt in prompt_versions.toml.
def active_version(name: str, path: Path = ACTIVE) -> str:
    with path.open("rb") as file:
        return tomllib.load(file)[name]
