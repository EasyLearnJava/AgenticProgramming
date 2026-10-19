# 17 · Prompts as versioned files

The greeting prompt moves out of the code and into text files, one file per version, so you can improve a prompt
without losing the old one, and tell which version wrote any answer. One line in `prompt_versions.toml` picks the
version in use: to roll back, you change that line.

```text
prompts/greeting.v1.md   the first try
prompts/greeting.v2.md   says who it's for, and how long
prompts/greeting.v3.md   asks for one concrete first project, no emoji      <- greeting = "v3" in prompt_versions.toml

POST /api/hello {"name": "Asha"}  ->  {"answer": "Welcome, Asha! ...", "prompt": "greeting", "version": "v3",
                                       "fingerprint": "c27b3feb"}
                                      (made-up answer: Gemini's words change every time; the fingerprint is real)
```

## What you'll build

- **Three versions of the greeting prompt** as plain text files, `prompts/greeting.v1.md` to `greeting.v3.md`, and
  **`prompt_versions.toml`**, whose one line `greeting = "v3"` picks the version in use.
- **`prompt_files.py`**: reads and checks every version when the program starts, and gives each file a fingerprint.
  A broken file stops the start with one line that says what to fix.
- **`hello.py`**: one chain per version. `python hello.py Asha v1` prints a welcome written with v1, then
  `(prompt: greeting v1, fingerprint c3b43ae2; the active version is v3)`.
- **A server and a page**: `GET /api/prompts` lists the versions, and `POST /api/hello` answers with the active
  version or the one you ask for. The page shows every version's text and fingerprint, has a version dropdown, and
  labels each answer with the version that wrote it, such as `greeting v3 (c27b3feb)`.

## What you'll learn

- **Prompt files**: a prompt is text for people to read, review and improve, so it lives outside the code.
- **Versions, not edits**: a change is a new file; a released file never changes.
- **Fingerprints**: the first 8 characters of a file's SHA-256 hash (`hashlib`) show which exact words wrote an
  answer, and a test makes sure the released files keep theirs.
- **A settings file picks the version**: `prompt_versions.toml`, read with Python's own `tomllib`. Rolling back is a
  one-line change and a restart.
- **`with_config(run_name=..., metadata=...)`**: labels every run of a chain, so a trace shows which prompt
  version produced it.
- **Check at start-up, not per request**: a broken prompt file stops the start, and an unknown `"version"` gets a
  422 from a Pydantic `field_validator`, before any call.

## What's new since project 16

- [Project 16 · Reasoning: chain-of-thought and thinking](../16-gemini-reasoning/README.md) wrote every prompt as a
  Python string in `hello.py` (`WAYS`, `BEFORE_PROMPT`, `AFTER_SYSTEM`, ...). Here the greeting's system and human
  messages are read from `prompts/greeting.vN.md` by a new file of code, `prompt_files.py`.
- `prompt_versions.toml` picks the version that answers: the code never names it.
- Each answer comes back labelled, `{"answer", "prompt", "version", "fingerprint"}`, and `POST /api/hello` takes an
  optional `"version"`, so you can compare versions on the same name. `hello.py` builds one chain per version, as
  project 16 built one per way, and labels each chain with `with_config()`.
- The task is the welcome for `{name}` from projects 10 to 12 again, so the only new things are where the prompt
  lives and how it's tracked. New Python pieces: `@dataclass`, `tomllib`, `hashlib` and Pydantic's
  `field_validator`.

## Before you start

- Python 3.11 or newer: `prompt_files.py` uses `tomllib`, which comes with Python from 3.11 on.
- The key from [project 9](../09-gemini-key/README.md). Each project folder reads its own `.env`, so copy yours into
  this one, once. From this folder, `projects/17-gemini-prompt-files`:

  ```bash
  cp ../09-gemini-key/.env .env
  ```

  With a Codespaces secret named `GOOGLE_API_KEY` there's nothing to copy: every project sees it.

## Files

| File | What it is |
|---|---|
| `prompts/greeting.v1.md`, `greeting.v2.md`, `greeting.v3.md` | The three versions of the greeting prompt: a note for people, then a `## system` and a `## human` section |
| `prompt_versions.toml` | One line per prompt: which version is in use (`greeting = "v3"`) |
| `prompt_files.py` | Reads and checks the files: `load_all()`, `active_version()` and `fingerprint()`. A broken file raises `PromptFileError` |
| `hello.py` | Loads every version at start, builds one chain per version, and labels each answer. `python hello.py [name] [version]` makes one real call |
| `main.py` | FastAPI: `GET /` and `/index.html` serve the page; `GET /api/prompts` lists the versions; `POST /api/hello` answers with the active version, or the one you ask for |
| `index.html` | The page: every version's text and fingerprint, a version dropdown, and the answers, each labelled with the version that wrote it |
| `config.py` | `load_api_key()`: loads `.env`, checks the key, and raises `MissingKeyError` with a clear message when there's none. The same file as project 9 |
| `.env.example` | The template for `.env`, the file that holds your key. `.env` is in `.gitignore`, so it never goes into git |
| `tests/test_hello.py` | The tests: plain ones that make no call, and a live one that calls Gemini once per version |
| `tests/conftest.py` | Runs before the tests and checks once for a real key: with none, it gives `hello.py` a fake one and skips the live test. The same file as project 10 |
| `pytest.ini` | Lets the tests import `hello` and `main` from this folder, only looks in `tests/`, and defines the `live` marker |
| `requirements.txt` | The packages, pinned: the same as project 10 |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |
| `README.md` | This page |

## How it works

### Why files?

Until now each prompt was a string in `hello.py`. That works until you change one: was yesterday's odd answer from
the old wording or the new one? With versioned files:

- An answer says `greeting v2 (89c586b3)`, so you can open `prompts/greeting.v2.md` and read the exact words.
- You can compare v1, v2 and v3 side by side on the page, with the same name.
- If v3 turns out worse, you set `greeting = "v2"` and restart: no code changes.
- Someone who doesn't write Python can still read a prompt and suggest a better one: it's just a text file.

### A prompt file

`prompts/greeting.v3.md`:

```markdown
# greeting v3: v2 was fine but vague, so ask for one concrete first project and no emoji

## system
You write short, friendly welcomes for people who are starting to learn LangChain.
Each welcome names one small thing they will build first, such as a chain that greets someone.
Use no emoji.

## human
Write a welcome for {name}, in at most two sentences.
```

- The `# ...` line at the top is a note for people: what changed, and why. Anything above the first heading is
  ignored, so it's never sent to Gemini.
- `## system` and `## human` become the system and human messages (project 13).
- `{name}` is filled in from the request, as before. As in project 13, `{` and `}` mark a slot to fill, so a brace
  you mean as plain text must be doubled: `{{` and `}}`.

The name says what it is: `<prompt>.v<number>.md`. Versions sort by number, so `v10` comes after `v9`.

### Loading: once, at start, and checked

`hello.py` reads every version when it starts, before the model is even built:

```python
# ① Load every version of the prompt once, at start, and check them all. A broken file stops the start-up here.
try:
    GREETINGS = load_all("greeting", needs={"name"})        # {"v1": PromptVersion(...), "v2": ..., "v3": ...}
    ACTIVE = active_version("greeting")                      # "v3", from prompt_versions.toml
    if ACTIVE not in GREETINGS:
        raise PromptFileError(f"prompt_versions.toml asks for greeting {ACTIVE}, but there's no prompts/greeting.{ACTIVE}.md")
except PromptFileError as err:
    sys.exit(f"Can't load the prompts: {err}")
```

`main.py` imports `hello.py`, so `python hello.py` and `uvicorn main:app` both stop at once on a broken file, with
one line instead of a traceback, rather than failing on some user's request later:

```text
Can't load the prompts: greeting.v2.md uses ['nmae'], but the code fills in ['name']
Can't load the prompts: prompt_versions.toml asks for greeting v9, but there's no prompts/greeting.v9.md
```

[When things go wrong](#when-things-go-wrong) lists every message. The next three sections walk through
`prompt_files.py`, the file that does the reading.

### Reading one file

```python
# ① Read one file: split it at the "## system" and "## human" headings.
def parse(path: Path, needs: set[str]) -> PromptVersion:
    name, version = path.name.removesuffix(".md").split(".", 1)        # "greeting.v3.md" -> "greeting", "v3"
    ...
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
```

- **The headings**: `re.MULTILINE` makes `^` and `$` match at the start and end of every line, so a heading must be
  a line of its own, written exactly `## system` or `## human` (spaces after it are allowed).
- **The template** is project 13's `ChatPromptTemplate.from_messages()`, with the two sections as its messages.
- **The variables**: `template.input_variables` lists the `{names}` the template found. A typo such as `{nmae}`
  doesn't match `needs={"name"}`, so the file is refused when the program starts, not when someone asks.
- **Line endings**: `read_text()` reads Windows line endings (`\r\n`, which Git on Windows may check a file out with)
  as `\n`, so a file is read, and fingerprinted, the same on Windows and in Codespaces.

What comes back is a `PromptVersion`:

```python
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
```

### Finding the versions, in order

```python
# ② Read every version of one prompt, in order: v1, v2, ... v10 (by number, not alphabetically).
def version_number(path: Path) -> int:
    """greeting.v10.md -> 10. Any other name, such as a copy called "greeting.v3 - Copy.md", is refused."""
    match = re.fullmatch(r"\w+\.v(\d+)\.md", path.name)
    if match is None:
        raise PromptFileError(f"{path.name} isn't named <prompt>.v<number>.md: rename it, or move it out of prompts/")
    return int(match.group(1))


def load_all(name: str, needs: set[str]) -> dict[str, PromptVersion]:
    paths = sorted(PROMPTS.glob(f"{name}.v*.md"), key=version_number)
    ...
    versions = [parse(path, needs) for path in paths]
    return {prompt.version: prompt for prompt in versions}         # {"v1": PromptVersion(...), "v2": ..., ...}
```

- `glob("greeting.v*.md")` finds every file whose name fits that pattern, in no promised order.
- `sorted(..., key=version_number)` sorts them by the number in the name. Sorted as text, `v10` would come before
  `v2`.
- A copy that Windows Explorer names `greeting.v3 - Copy.md` (or VS Code `greeting.v3 copy.md`) fits the glob, but
  `3 - Copy` isn't a number, so `version_number()` refuses it with a message instead of a crash.

### Which version is active

`prompt_versions.toml` is a small settings file in TOML, a format made for settings: `name = "value"`, one per line.

```toml
# Which version of each prompt the server uses. The files are in prompts/, named <prompt>.<version>.md.
# To roll back, change the version here and restart the server. Nothing else changes.
greeting = "v3"
```

```python
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
```

The two likely mistakes, `greeting = v2` (no quotes, so it isn't valid TOML) and a misspelled name, each become a
`PromptFileError` with a message, like a broken prompt file.

### The fingerprint: proof of the exact words

```python
def fingerprint(text: str) -> str:
    """The first 8 characters of the text's SHA-256 hash: "c27b3feb" for prompts/greeting.v3.md."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
```

A hash turns any text into a fixed-length code. Change one word, even one character, and the code changes
completely. The first 8 characters are plenty to tell a handful of versions apart.

The tests keep the fingerprint of every released version:

```python
RELEASED = {"v1": "c3b43ae2", "v2": "89c586b3", "v3": "c27b3feb"}
...
@pytest.mark.parametrize("version, released", RELEASED.items())
def test_released_versions_are_never_edited(version, released):
    assert hello.GREETINGS[version].fingerprint == released
```

If someone edits a released file, its test fails: `test_released_versions_are_never_edited[v2-89c586b3]` for
`greeting.v2.md`. Without this check, an answer labelled `v2` might no longer match `greeting.v2.md`, and the label
would be worthless. The fix is to undo the edit and save the change as a new version.

### One chain per version, labelled

```python
# ② One chain per version. prompt is a PromptVersion (prompt_files.py), and prompt.template its ChatPromptTemplate.
#    with_config() attaches the version to every run of that chain, so a trace (in a tracing tool such as LangSmith)
#    shows which prompt produced the answer, not only the answer.
def make_chain(prompt: PromptVersion):
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
    return {"answer": answer, **label(version)}          # ** copies label's three keys into this dict
```

The version travels with every answer in three places:

- **In the answer**: `greet()` returns the answer with `prompt`, `version` and `fingerprint`.
- **In the server's terminal**: every answer is logged as `answered with prompt greeting v3 (c27b3feb)`.
- **In traces**: `with_config()` attaches a name and metadata to every run of that chain, so if you turn on a tracing
  tool such as LangSmith, each trace shows which prompt version produced it, with no change to the code.
  [Things to try](#things-to-try) shows the label without any tool. LangSmith also has a "prompt hub" that stores
  versioned prompts as a service: the same idea, hosted.

### The server: asking for a version

```python
class HelloIn(BaseModel):
    """The JSON body: a name, and which version of the prompt to use. Checked before any model call."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Asha " -> "Asha", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)
    version: str | None = None                 # leave it out to use the active version

    # The versions are only known once the files are read, so a Literal["v1", "v2", "v3"] (projects 5 and 15) can't
    # list them: this check does. Pydantic runs it on "version" before the route runs, and a ValueError raised here
    # becomes the usual 422.
    @field_validator("version")
    @classmethod
    def known_version(cls, version):
        if version is not None and version not in hello.GREETINGS:
            raise ValueError(f"no such version: the versions are {', '.join(hello.GREETINGS)}")
        return version
...
@app.post("/api/hello")
async def say_hello(body: HelloIn):
    """A welcome for the name, written with the version asked for (or the active one), and labelled with it."""
    version = body.version or hello.ACTIVE          # no "version" in the body: the one prompt_versions.toml picks
```

- **An unknown version never reaches Gemini.** `{"version": "v9"}` gets a 422 with
  `Value error, no such version: the versions are v1, v2, v3`, before any call. Pydantic calls the validator on the
  class, before any `HelloIn` object exists, which is why it's a `@classmethod`.
- **Leaving `"version"` out** (or sending `null`) uses the active one.
- **A failed call is a 502**, as in project 10: the page gets `Gemini didn't answer (TypeName).`, and the full reason
  goes to the server's terminal.
- `GET /api/prompts` returns `{"active": "v3", "versions": {...}}`: each version's `system` and `human` text, and
  its fingerprint.

### The page

On load, the page calls `GET /api/prompts` to fill the versions table and the dropdown, with the active version
marked `(active)` and picked. **Ask Gemini** sends `{"name", "version"}` to `POST /api/hello`. Each answer goes at
the top of the answers table, labelled with the version and fingerprint that wrote it, so after a few tries you can
compare the versions' answers side by side.

| The server answers | The page shows |
|---|---|
| 200 | the answer, labelled like `greeting v3 (c27b3feb)` |
| 422 | what was wrong, for example `name: String should have at least 1 character` |
| 502 | `Gemini didn't answer (GoogleInvalidRequestError). The server's terminal says why.` |
| any other status, or nothing at all | `Something went wrong: the server answered HTTP 500`, or `Something went wrong: Failed to fetch` |

### Adding a version, and rolling back

To improve the prompt:

1. **Write it.** Copy `prompts/greeting.v3.md` to `prompts/greeting.v4.md` and edit the copy. Say what changed, and
   why, in the `#` line. The tests still pass: a new file is a draft, and you can change it as often as you like.
2. **Try it.** Run `python hello.py Asha v4`. Or restart the server (it reads the files only when it starts) and
   pick `v4` in the dropdown, next to the older versions.
3. **Release it.** When it's better, set `greeting = "v4"` in `prompt_versions.toml`, add `"v4": "<its fingerprint>"`
   to `RELEASED` in `tests/test_hello.py` (the page shows the fingerprint), and restart the server. From then on v4
   is guarded like the others: `test_the_active_version_is_a_released_one` fails until you add it.

To roll back, set `greeting = "v3"` again and restart. The old file never changed, so v3 sends Gemini exactly the
words it sent before. The answers still vary from call to call, as they always do.

## Run it

```bash
cd projects/17-gemini-prompt-files
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

Then, with the `.env` copied in (see [Before you start](#before-you-start)):

```bash
python config.py                     # GOOGLE_API_KEY is set.  (or a message saying what to do)
python hello.py                      # a welcome for Raghu from the active version: one real call
python hello.py Asha v1              # one for Asha from v1, to compare
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

`python hello.py Asha v1` prints the welcome, then the version that wrote it:

```text
Welcome, Asha! We're so glad you're here. Whether you're joining us to learn, to share or to explore, ...

(prompt: greeting v1, fingerprint c3b43ae2; the active version is v3)
```

(The welcome is a made-up example: Gemini's words change every time, and v1, which asks for nothing more than "a
welcome", tends to get long, generic ones. The last line is real.)

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous project's server (Ctrl+C) before starting this one.

`uvicorn --reload` restarts by itself when a `.py` file changes, but not when a prompt file or
`prompt_versions.toml` changes: press Ctrl+C and start it again after editing those.

The curl examples are for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl http://127.0.0.1:8000/api/prompts
# {"active":"v3","versions":{"v1":{"system":"You write welcome messages.","human":"Write a welcome for {name}.","fingerprint":"c3b43ae2"},...}}

curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha", "version": "v1"}'
# {"answer":"...","prompt":"greeting","version":"v1","fingerprint":"c3b43ae2"}   one real call: new words every time

curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha", "version": "v9"}'
# {"detail":[{"type":"value_error","loc":["body","version"],"msg":"Value error, no such version: the versions are v1, v2, v3",...}]}
# a 422, and no call to Gemini
```

Every click and every `curl` to `/api/hello` with a good body is a real call to Gemini, and uses your key's quota.

## Test it

```bash
python -m pytest                     # every test; the live one is skipped when there's no key
python -m pytest -m "not live"       # only the plain tests: no call, no cost
python -m pytest -m live             # only the live test: three real calls, one per version
```

There are 33 tests: 32 plain and 1 live.

- **The 32 plain tests** never call Gemini:
  - the prompt files (13): every released version loads, in order, and still has its `RELEASED` fingerprint (4);
    a file becomes a system and a human message, and the note at the top isn't sent (2); a file with Windows line
    endings gets the same fingerprint, and one changed word changes it (2); a broken file is refused (5): a missing
    section, an empty one, two `## system` sections, a misspelled variable, and a brace without its partner
  - the names and the active version (6): `v10` sorts after `v9`; a copy named `greeting.v3 - Copy.md` is refused;
    the active version comes from `prompt_versions.toml`, and a one-line roll-back changes it; the active version is
    a released one; a `prompt_versions.toml` without quotes, or with a misspelled name, is refused (2)
  - the model and the chains (3): the model's name and cap; each chain's run name and metadata; `greet()` labels
    the answer with its version
  - starting (2): with no key, and with a stray copy in `prompts/`, `python hello.py` stops with one line and no
    traceback
  - the endpoints (6): `/api/prompts` lists every version and the active one; `/api/hello` uses the active version
    by default, or the one asked for; an empty name and an unknown version each get a 422, and no chain runs (2); a
    failed call gets a 502 with only the error's type, while the full reason goes to the server's log
  - the page (2): `/` and `/index.html` are served, with no key in them
- **The live test** sends each version to Gemini once and checks that each one gets an answer. It can't check the
  words, because they change every time.

No test assumes that v3 is the active version: they take it from `prompt_versions.toml` (through `hello.ACTIVE`),
so they still pass after a roll-back, or when you add a version. `RELEASED` is the one place that pins what the
released files say.

For the endpoint tests, every version's chain is swapped for a small stand-in,
`monkeypatch.setitem(hello.chains, version, ...)`, so they need no key and no network. `tests/conftest.py` runs
first and checks once for a real key. With one, every test runs. With none, it gives `hello.py` a fake key so it can
be imported, and skips the live test with `live test: needs GOOGLE_API_KEY (see project 9)`.

Without a key, `python -m pytest` ends with `32 passed, 1 skipped`, and `python -m pytest -m "not live"` with
`32 passed, 1 deselected`.

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| A copy left in `prompts/`, such as Windows Explorer's `greeting.v3 - Copy.md` | `Can't load the prompts: greeting.v3 - Copy.md isn't named <prompt>.v<number>.md: rename it, or move it out of prompts/` | Rename it to the next version (`greeting.v4.md`), or move it out of `prompts/` |
| A misspelled variable, such as `{nmae}` | `Can't load the prompts: greeting.v2.md uses ['nmae'], but the code fills in ['name']` | Write `{name}` |
| A brace without its partner, such as `{name`, or more than a name between the braces, such as `{name.upper}` | `Can't load the prompts: greeting.v2.md has braces that don't make a variable: expected '}' before end of string` (for `{name.upper}`, the end says `Invalid variable name 'name.upper' ...`) | Write `{name}`: both braces, and only the name between them. For a brace that is plain text, write `{{` or `}}` |
| A section missing, empty, doubled, or with a different heading (`## System`, `## user`) | `Can't load the prompts: greeting.v1.md needs a '## system' and a '## human' section, each with some text` | One `## system` line and one `## human` line, in lower case, each followed by some text |
| A mistake in `prompt_versions.toml` | `... isn't valid TOML (Invalid value (at line 3, column 12)): write it as greeting = "v3"` (the quotes are missing), `... doesn't say which greeting version to use ...` (the name is misspelled), or `... asks for greeting v9, but there's no prompts/greeting.v9.md` | Write the line as `greeting = "v3"`, naming a version that has a file |
| Any of the above with `uvicorn main:app --reload` | The message appears, but the command keeps running, still saying `Uvicorn running on ...`, and the page won't open | Fix the file, then press Ctrl+C and start the server again: `--reload` restarts it only when a `.py` file changes |
| Any of the above while running `pytest` | pytest stops before any test runs, with a long `INTERNALERROR` traceback. Its last line is the same message: `INTERNALERROR> SystemExit: Can't load the prompts: ...` | Run `python hello.py` to see just the message, and fix the file |
| You edited a released file | `FAILED tests/test_hello.py::test_released_versions_are_never_edited[v2-89c586b3]`, with `assert '54a77e6c' == '89c586b3'` (the new fingerprint, then the released one) | Undo the edit (your editor's undo, or `git restore prompts/greeting.v2.md`), and save the change as a new version |
| You made a new version active, but didn't add it to `RELEASED` | `FAILED tests/test_hello.py::test_the_active_version_is_a_released_one`, with `assert 'v4' in {'v1': 'c3b43ae2', ...}` | Add `"v4": "<its fingerprint>"` to `RELEASED` in `tests/test_hello.py` |
| The page doesn't show a new version, or marks the old one active | Nothing changes after you edit `prompts/` or `prompt_versions.toml` | The server read the files when it started, and `--reload` only watches `.py` files: press Ctrl+C and start it again |
| No key, a wrong key, no quota or no network | The same as in project 10, for example a 502 with `Gemini didn't answer (GoogleInvalidRequestError).` | See [project 10's table](../10-gemini-llm/README.md#when-things-go-wrong), which also explains the harmless `automatic function calling (AFC)` warning in the terminal |

## Things to try

1. **Roll back.** Set `greeting = "v2"` in `prompt_versions.toml` and restart the server. The page marks
   `v2 (active)` and picks it in the dropdown, and new answers are labelled `greeting v2 (89c586b3)`.
   `python -m pytest -m "not live"` still passes, because no test assumes v3. Set it back to `"v3"`.
2. **Edit a released file on purpose.** In `prompts/greeting.v2.md`, change `friendly` to `cheerful` and run
   `python -m pytest -m "not live"`. Exactly one test fails, `test_released_versions_are_never_edited[v2-89c586b3]`,
   with `assert '54a77e6c' == '89c586b3'`: one changed word gave the file a new fingerprint. Undo the edit.
3. **Break a file on purpose.** Change `{name}` to `{nmae}` in `prompts/greeting.v2.md` and run `python hello.py`.
   It stops before any call with `Can't load the prompts: greeting.v2.md uses ['nmae'], but the code fills in
   ['name']`. Undo it. Then copy `greeting.v3.md` in Explorer or VS Code, leave the copy in `prompts/`, and run
   `python hello.py` again: the copy's name is refused. Delete the copy.
4. **See the label a trace gets.** Start `python` in this folder and run `import hello`, then
   `hello.chains["v1"].config`. It shows what every run of the v1 chain carries, with no call:
   `{'run_name': 'greeting.v1', 'metadata': {'prompt': 'greeting', 'prompt_version': 'v1', 'prompt_fingerprint': 'c3b43ae2'}}`.
   To watch one real call step by step, run
   `from langchain_core.tracers import ConsoleCallbackHandler` and then
   `hello.chains["v1"].invoke({"name": "Asha"}, config={"callbacks": [ConsoleCallbackHandler()]})`: each step
   prints under the chain's name, such as `[chain:greeting.v1 > prompt:ChatPromptTemplate]`.

## Next

**Coming next: the same call without a framework**: the welcome written straight against `google-genai`, Google's
own library (the one `langchain-google-genai` has been using underneath), to see what LangChain has been doing for
you. That project isn't written yet.
