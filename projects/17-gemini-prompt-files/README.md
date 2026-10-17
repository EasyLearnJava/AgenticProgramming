# 17 · Prompts as versioned files

The prompt moves out of the code into files: one file per version, in `prompts/`. One line in
`prompt_versions.toml` picks the version in use, and every answer says which version produced it. To change a
prompt, add a new version; to roll back, change that one line.

```text
prompts/greeting.v1.md   the first try
prompts/greeting.v2.md   says who it's for, and how long
prompts/greeting.v3.md   asks for one concrete first project, no emoji      <- greeting = "v3" in prompt_versions.toml

POST /api/hello {"name": "Asha"}  ->  {"answer": "Welcome, Asha! ...", "prompt": "greeting", "version": "v3",
                                       "fingerprint": "c27b3feb"}
```

## What you learn

- **Prompt files**: prompts are text for people to read, review and improve, so they live outside the code
- **Prompt versions**: a change is a new file, and old versions stay exactly as they were
- **Traceable answers**: each answer carries its prompt's version and a fingerprint of the exact words
- **Rolling back** is a one-line config change

## Why bother?

Until now each prompt was a string in `hello.py`. That works until you change one: was yesterday's odd answer from
the old wording or the new one? With versioned files:

- An answer says `greeting v2 (89c586b3)`, so you can open `prompts/greeting.v2.md` and read the exact words.
- You can compare v1, v2 and v3 side by side on the page, with the same name.
- If v3 turns out worse, you set `greeting = "v2"` and restart: no code changes.
- Someone who doesn't write Python can still read and suggest a prompt: it's just a text file.

## Before you start: the key

As in project 10, copy your `.env` across (or use a Codespaces secret):

```bash
cd projects/17-gemini-prompt-files
cp ../10-gemini-llm/.env .env
python config.py                   # GOOGLE_API_KEY is set.
```

## Files

| File | What it is |
|---|---|
| `prompts/greeting.v1.md`, `v2.md`, `v3.md` | The three versions of the greeting prompt |
| `prompt_versions.toml` | One line per prompt: which version is in use (`greeting = "v3"`) |
| `prompt_files.py` | Reads and checks the files: `load_all()`, `active_version()`, `fingerprint()` |
| `hello.py` | Loads every version at start, builds one chain per version, and labels each answer. `python hello.py Asha v1` tries a version |
| `config.py` | Loads and checks the key: the same file as projects 9 to 16 |
| `main.py` | FastAPI: `GET /api/prompts` lists the versions; `POST /api/hello` answers with the active version, or the one you ask for |
| `index.html` | The page: every version's text and fingerprint, a version dropdown, and the answers, each with the version that produced it |
| `tests/test_hello.py` | 24 plain tests (no call) and 1 live test (one call per version) |
| `requirements.txt` | The same as project 10 |

## A prompt file

```markdown
# greeting v3: v2 was fine but vague, so ask for one concrete first project and no emoji

## system
You write short, friendly welcomes for people who are starting to learn LangChain.
Each welcome names one small thing they will build first, such as a chain that greets someone.
Use no emoji.

## human
Write a welcome for {name}, in at most two sentences.
```

- The `# ...` line at the top is a note for people: what changed, and why. It isn't sent to Gemini.
- `## system` and `## human` become the system and human messages (project 13).
- `{name}` is filled in from the request, as before.

The name says what it is: `<prompt>.<version>.md`. Versions sort by number, so `v10` comes after `v9`.

## Loading: once, at start, and checked

```python
GREETINGS = load_all("greeting", needs={"name"})      # {"v1": PromptVersion(...), "v2": ..., "v3": ...}
ACTIVE = active_version("greeting")                    # "v3", from prompt_versions.toml
```

Every file is read and checked when the server starts. A broken one stops the start-up with a clear message,
rather than failing on some user's request later:

```text
Can't load the prompts: greeting.v2.md uses ['nmae'], but the code fills in ['name']
Can't load the prompts: prompt_versions.toml asks for greeting v9, but there's no prompts/greeting.v9.md
```

## The fingerprint: proof of the exact words

```python
fingerprint(text)   # the first 8 characters of the file's SHA-256 hash: "c27b3feb"
```

Change one word in a file, and its fingerprint changes. Line endings are made the same before hashing, so the file
gives the same fingerprint on Windows (`\r\n`) and in Codespaces (`\n`).

The tests keep the fingerprint of every released version:

```python
RELEASED = {"v1": "c3b43ae2", "v2": "89c586b3", "v3": "c27b3feb"}
```

If someone edits an old version's file, the test fails. Then any answer labelled `v2` would no longer match
`greeting.v2.md`, which is the whole point of the label. The fix is to undo the edit and save the change as a new
version.

## The version travels with every answer, and every trace

```python
(prompt.template | model | StrOutputParser()).with_config(
    run_name="greeting.v3",
    metadata={"prompt": "greeting", "prompt_version": "v3", "prompt_fingerprint": "c27b3feb"},
)
```

- **In the answer:** `greet()` returns the answer with `prompt`, `version` and `fingerprint`.
- **In the server's terminal:** every answer is logged as `answered with prompt greeting v3 (c27b3feb)`.
- **In traces:** `with_config()` attaches the version to every run of that chain. When a later project turns on
  LangSmith tracing, each trace shows which prompt version produced it, with no other change. LangSmith also has a
  "prompt hub" that stores versioned prompts as a service: the same idea, hosted.

## Adding a version, and rolling back

To improve the prompt:

1. Copy `prompts/greeting.v3.md` to `prompts/greeting.v4.md`, and edit the copy. Say what changed in the `#` line.
2. Add its fingerprint to `RELEASED` in the tests (the page shows it).
3. Try it: pick `v4` in the dropdown, or run `python hello.py Asha v4`.
4. When it's better, set `greeting = "v4"` in `prompt_versions.toml`, and restart.

To roll back, set `greeting = "v3"` and restart. The old files never changed, so v3 answers exactly as it did.

## Run it

```bash
cd projects/17-gemini-prompt-files
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../10-gemini-llm/.env .env      # the key, once (see above)

python hello.py                    # a welcome for Raghu, with the active version
python hello.py Asha v1            # with v1, to compare
python -m pytest                   # 25 tests: 24 plain, 1 live
python -m pytest -m "not live"     # only the plain ones: no call, no cost

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

```bash
curl -X POST http://127.0.0.1:8000/api/hello -H "Content-Type: application/json" -d '{"name": "Asha", "version": "v1"}'
```

`uvicorn --reload` restarts by itself when a `.py` file changes, but not when a prompt file or
`prompt_versions.toml` changes: press Ctrl+C and start it again after editing those.

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Part B's next module chooses models and paths: the same call without LangChain, comparing models, and running an
open model yourself.
