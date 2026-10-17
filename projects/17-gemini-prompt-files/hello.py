"""
Project 17: prompts as versioned files. The greeting prompt is no longer written in the code: it's read from
prompts/greeting.v1.md, v2.md and v3.md, and prompt_versions.toml says which one is in use. Every answer says which
version produced it.

    greet("Asha")        ->  {"answer": "...", "prompt": "greeting", "version": "v3", "fingerprint": "1a2b3c4d"}
    greet("Asha", "v1")  ->  the same, with an older version, to compare

Run it on its own:   python hello.py         ->   a welcome for Raghu with the active version
                     python hello.py Asha v1 ->   for Asha, with v1
main.py imports from here and serves it at POST /api/hello.
"""
import sys

from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MissingKeyError, load_api_key
from prompt_files import PromptFileError, active_version, load_all

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 300

try:
    api_key = load_api_key()
except MissingKeyError as err:
    sys.exit(f"Can't build the chain: {err}")

# ① Load every version of the prompt once, at start, and check them all. A broken file stops the start-up here.
try:
    GREETINGS = load_all("greeting", needs={"name"})
    ACTIVE = active_version("greeting")
    if ACTIVE not in GREETINGS:
        raise PromptFileError(f"prompt_versions.toml asks for greeting {ACTIVE}, but there's no prompts/greeting.{ACTIVE}.md")
except PromptFileError as err:
    sys.exit(f"Can't load the prompts: {err}")

model = ChatGoogleGenerativeAI(model=MODEL, google_api_key=api_key, max_output_tokens=MAX_OUTPUT_TOKENS)


# ② One chain per version. with_config() attaches the version to every run of that chain, so a trace (LangSmith,
#    later) shows which prompt produced the answer, not only the answer.
def make_chain(prompt):
    return (prompt.template | model | StrOutputParser()).with_config(
        run_name=f"{prompt.name}.{prompt.version}",
        metadata={"prompt": prompt.name, "prompt_version": prompt.version, "prompt_fingerprint": prompt.fingerprint},
    )


chains = {version: make_chain(prompt) for version, prompt in GREETINGS.items()}


# ③ The answer travels with its version: which prompt, which version, which exact file text.
def label(version: str) -> dict:
    prompt = GREETINGS[version]
    return {"prompt": prompt.name, "version": prompt.version, "fingerprint": prompt.fingerprint}


async def greet(name: str, version: str = ACTIVE) -> dict:
    answer = await chains[version].ainvoke({"name": name})
    return {"answer": answer, **label(version)}


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Raghu"
    version = sys.argv[2] if len(sys.argv) > 2 else ACTIVE
    if version not in GREETINGS:
        sys.exit(f"No version {version!r}: there are {', '.join(GREETINGS)}")
    print(chains[version].invoke({"name": name}))
    print(f"\n(prompt: greeting {version}, fingerprint {GREETINGS[version].fingerprint}; the active version is {ACTIVE})")
