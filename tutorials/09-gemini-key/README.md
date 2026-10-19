# 09 · Get a Gemini key and keep it secret

Before the first model call: create a Gemini API key, cap what it can spend, and keep it on the server, where the
page and git never see it. `config.py` loads and checks the key, and the server refuses to start without one; the
first real call to Gemini comes in project 10.

```text
python config.py            ->  GOOGLE_API_KEY is set.                (the key itself is never printed)
GET /api/status             ->  {"key_set": true}                     (never the key itself)
no key at start-up          ->  Can't start the server: GOOGLE_API_KEY is not set. Copy .env.example to .env ...
```

## What you'll build

- **A Gemini API key** in Google Cloud, restricted to the Gemini API and covered by a budget alert, kept in this
  folder's `.env` (or a Codespaces secret) and never in git.
- **`config.py`**: `load_api_key()` stops with a one-line message when the key is missing, blank, still the
  placeholder, or in a `.env` that isn't UTF-8 text. `python config.py` prints `GOOGLE_API_KEY is set.`, never
  the key.
- **`main.py`**: a FastAPI server that checks the key as it starts (no key, no server). `GET /api/status` answers
  `{"key_set": true}`.
- **`index.html`**: a page that asks `/api/status` when it opens. Its source and the browser's Network tab show
  no key.

## What you'll learn

- **An API key**: a password for your account. Whoever has it can call the model, and you pay for it
- **Environment variables and `python-dotenv`**: `load_dotenv()` sets them from `.env`, and `os.getenv()` reads them
- **Fail fast with your own error**: `class MissingKeyError(RuntimeError)`, `raise`, `try`/`except`, `sys.exit()`
- **The key stays on the server**: never in a response, never in the page, never in git
- **`.gitignore` and `.env.example`**: git never sees `.env`; the committed example holds only a placeholder
- **Testing settings**: `monkeypatch.setenv()`/`delenv()`, `tmp_path`, and a subprocess with a chosen environment

## What's new since project 08

- [Project 08 · Vibe-code a data app](../08-vibecode-data-app/README.md) was a Streamlit app. This one is back to the
  FastAPI server and plain page of projects 2 to 7: `GET /` and `/index.html` serve the page, plus one route,
  `GET /api/status`.
- No chain and no LangChain this time (the packages are `fastapi`, `uvicorn` and `python-dotenv`). There's no
  `hello.py`: the script you run on its own is `python config.py`.
- New files: `config.py`, `.env.example` and your own `.env`. New package: `python-dotenv`, which reads `.env`.
- New Python: environment variables, `try`/`except`, an error class of our own and `sys.exit()`. New in the tests:
  `monkeypatch`, `tmp_path`, `skipif`, and running a script with `GOOGLE_API_KEY` emptied for that one run.

## Before you start

- Python 3.11 or newer.
- A Google account and a Google Cloud project to hold the key (step 1 picks it).
- No real key is needed to run the tests: they use fake ones.

Then make the key, cap what it can spend, and put it where only the server can read it: steps 1 to 3.

### 1. Create the key

**GO TO https://console.cloud.google.com/apis/credentials AND DO THIS:**

1. **PICK YOUR PROJECT IN THE PROJECT LIST AT THE TOP OF THE PAGE.**
2. **CLICK "CREATE CREDENTIALS", THEN "API KEY".**
3. **NAME: GIVE THE KEY A CLEAR NAME, FOR EXAMPLE "AGENTICPROGRAMMING SERVER KEY".**
4. **API RESTRICTIONS: CHOOSE "RESTRICT KEY" AND TICK ONLY "GEMINI API".**
   **NOT "GEMINI FOR GOOGLE CLOUD API": THAT IS A DIFFERENT SERVICE.**
5. **APPLICATION RESTRICTIONS: CHOOSE "NONE".**
   **NOT "WEBSITES": THE SERVER SENDS NO WEBSITE ADDRESS, SO GOOGLE WOULD BLOCK EVERY CALL WITH
   "403 PERMISSION_DENIED: REQUESTS FROM REFERER &lt;EMPTY&gt; ARE BLOCKED".**
6. **CLICK "CREATE" (OR "SAVE"), THEN COPY THE KEY FROM THE BOX THAT APPEARS.**
7. **CHECK THE API KEYS LIST: THE NEW KEY'S RESTRICTIONS SHOULD SAY "1 API".**
8. **WAIT UP TO 5 MINUTES: NEW SETTINGS TAKE A LITTLE WHILE TO WORK.**

**DON'T USE A KEY CALLED "BROWSER KEY (AUTO CREATED BY FIREBASE)". IT IS MADE FOR WEB PAGES, IS LOCKED TO
WEBSITES, AND IS USUALLY PUBLIC INSIDE YOUR FIREBASE SITE. MAKE A SEPARATE KEY FOR THE SERVER AND LEAVE THAT ONE
AS IT IS.**

**NEVER PASTE THE KEY INTO A CHAT OR SHOW IT IN A SCREENSHOT. IF YOU DO, CLICK THE KEY IN THE LIST, CLICK "ROTATE
KEY" (OR DELETE IT AND MAKE A NEW ONE), AND USE THE NEW VALUE.**

A key looks like `AIza…` (older keys) or `AQ.…` (newer keys, bound to a service account). Both work the same way
here.

### 2. Cap the spend, before the first call

- **Budget alert:** in the Google Cloud console, for the key's project, go to **Billing → Budgets & alerts** and set
  a small budget, for example $5, with email alerts.
- **Quota (optional, a hard limit):** in **APIs & Services → Gemini API → Quotas**, lower the
  requests per minute or per day.

A budget alert only warns you, while a quota actually stops the calls. Every project from 10 on also sets
`max_output_tokens` on each call, a cap on the length of each answer.

### 3. Put the key where only the server can read it

Pick **one** of these:

**A `.env` file** (on your laptop, or in Codespaces):
```bash
cd tutorials/09-gemini-key
cp .env.example .env               # then open .env and replace your-key-here with your key
```
`config.py` reads the `.env` in its own folder, this one. `.env` is in the repo's `.gitignore`, so git never sees
it. `.env.example` is committed, so it must only ever hold the placeholder. Each later project reads the `.env` in
its own folder too: from project 10 on, you copy this one across with `cp ../09-gemini-key/.env .env`.

**A Codespaces secret** (keeps the key out of every file, and every project sees it): on GitHub go to **Settings →
Codespaces → Secrets → New secret**, name it `GOOGLE_API_KEY`, and give it access to this repository. Then stop and
restart the codespace (or create a new one): a running codespace doesn't see a new secret.

In production, the same variable goes in the hosting provider's environment variables.

**Never** paste the key into the code, the page, a commit, a screenshot or a chat with an AI assistant. If it leaks,
rotate it (or delete it) on the Credentials page and use the new one.

## Files

| File | What it is |
|---|---|
| `config.py` | `load_api_key()`: loads `.env`, reads `GOOGLE_API_KEY`, and raises `MissingKeyError` with a clear message when there's no usable key. `python config.py` checks it from the terminal. Projects 10 to 17 have this same file |
| `main.py` | FastAPI: checks the key when it starts (no key, no server), serves the page, and answers `GET /api/status` with `{"key_set": true}` |
| `index.html` | The page: asks `/api/status` when it opens and shows the answer |
| `.env.example` | The template for `.env`: `GOOGLE_API_KEY=your-key-here`. It's committed, so it only ever holds the placeholder |
| `.env` | Your real key. You make it in step 3; it isn't in the repo, and git ignores it |
| `tests/test_config.py` | The tests, all with fake keys: where the key is read from, the clear errors, the server with no key, that no response or page holds the key, and that git ignores `.env` |
| `pytest.ini` | pytest's settings: lets the tests `import config` and `import main` from this folder, and looks for tests only in `tests/` |
| `requirements.txt` | `fastapi`, `uvicorn`, `python-dotenv`: no LangChain this time |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |
| `README.md` | This page |

## How it works

The key's way from `.env` to the server, in the order the code runs.

### 1. `load_dotenv()` copies `.env` into the environment

`config.py`:

```python
ENV_FILE = Path(__file__).with_name(".env")
...
# ① Load: copy the lines of .env into the environment, then read the key from there.
#    load_dotenv() doesn't overwrite a variable that's already set, so a key set outside the file (a Codespaces
#    secret, or the hosting provider's settings in production) wins over the file.
def load_api_key(env_file: Path = ENV_FILE) -> str:
    try:
        load_dotenv(env_file)
    except UnicodeDecodeError:
        # A common Windows surprise: PowerShell 5's `echo ... > .env` saves the file as UTF-16, which can't be read.
        raise MissingKeyError(
            f"{env_file.name} isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding."
        ) from None
```

- An **environment variable** is a name and a value that a program gets from whatever started it: your terminal,
  Codespaces, a hosting provider. In Python they are in `os.environ`.
- `Path(__file__).with_name(".env")` is the `.env` in the same folder as `config.py`, so it's found whichever folder
  you start Python from.
- `load_dotenv()` reads each `NAME=value` line of `.env` and adds it to the environment. It never overwrites a
  variable that is already set, even to an empty value. So if the key is set in both places, the environment wins:
  a Codespaces secret beats a `.env` file.
- python-dotenv reads `.env` as UTF-8 text. A file saved as UTF-16 makes it raise `UnicodeDecodeError`, which
  `load_api_key()` turns into a `MissingKeyError` that says what to do. `from None` leaves the original error out of
  the report: the message says it all.

### 2. `os.getenv()` reads the key, and two checks fail fast

```python
# Our own kind of error, for exactly one problem: "there's no usable key". The code that calls load_api_key() can
# catch just this error and print its message, while any other error still shows up as a normal traceback.
class MissingKeyError(RuntimeError):
    """There's no usable GOOGLE_API_KEY. The message says how to set one."""
...
    key = os.getenv("GOOGLE_API_KEY", "").strip()

    # ② Fail fast: stop now with a clear message, rather than later with a confusing error from the first model call.
    if not key:
        raise MissingKeyError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, "
            "or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret)."
        )
    if key == PLACEHOLDER:
        raise MissingKeyError("GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.")
    return key
```

- `os.getenv("GOOGLE_API_KEY", "")` gives `""` instead of `None` when the variable doesn't exist, so `.strip()`
  always works. `.strip()` removes spaces and line breaks from both ends, so a key of only spaces counts as missing.
- `MissingKeyError` is an error type of our own (in Java: `class MissingKeyError extends RuntimeException`), and
  `raise` throws it. Whoever calls `load_api_key()` can catch exactly this problem and turn it into one line, while
  any other error still shows in full.
- These checks only look at whether there is a key, not whether Google accepts it: this project never calls Gemini.
  A wrong key shows up in project 10, at the first call.

### 3. `python config.py`: one line, not a traceback

```python
if __name__ == "__main__":
    try:
        load_api_key()
    except MissingKeyError as err:
        sys.exit(str(err))                   # prints the message and exits with code 1: no stack trace
    print("GOOGLE_API_KEY is set.")          # never print the key itself, not even part of it
```

- `try`/`except` is Python's try/catch. `except MissingKeyError as err` catches only our error; `err` is the error
  object, and `str(err)` is its message.
- `sys.exit("some text")` prints the text to the terminal (on stderr) and ends the program with exit code 1. Code 0
  means a program succeeded and anything else means it failed; the tests check both.

### 4. `main.py` checks the key the moment uvicorn imports it

```python
# ① The fail-fast check. It runs once, when uvicorn imports this module, before the server answers anything:
#    no key, no server.
try:
    GOOGLE_API_KEY = load_api_key()          # kept here, on the server: nothing in this project sends it anywhere
except MissingKeyError as err:
    sys.exit(f"Can't start the server: {err}")   # one line in the terminal, exit code 1, no traceback

# ② The server. It is only built if ① found a key, and neither route ever puts the key in its answer.
app = FastAPI(title="AgenticProgramming project 9")
```

- Code at the top level of a module, outside any function, runs once, when the module is first imported.
  `uvicorn main:app` imports `main` to find `app`, so the check runs before the server answers anything. With no
  key, `sys.exit` stops the import, and uvicorn stops too.
- With `--reload`, uvicorn first prints `Uvicorn running on http://127.0.0.1:8000`, then the message, and keeps
  waiting, but nothing answers on port 8000. It restarts only when a `.py` file changes, so creating `.env` doesn't
  restart it: press Ctrl+C and start it again.

### 5. `/api/status` and the page: a yes, never the key

```python
@app.get("/api/status")
async def status():
    """Says the key is set. If it weren't, the server wouldn't be running to answer."""
    return {"key_set": True}
```

`index.html`:

```js
    fetch("/api/status")
      .then((res) => {
        // An error answer, such as a 404 or a 500, still arrives as an answer: check res.ok and make it an error.
        if (!res.ok) throw new Error(`the server answered HTTP ${res.status}`);
        return res.json();
      })
```

- `/api/status` can only ever answer `true`: without a key, there is no server to answer.
- The page checks `res.ok` before it reads the answer. If the route were renamed (a 404) or broke (a 500), the page
  says `Something went wrong: the server answered HTTP 404` instead of wrongly saying there's no key.

### Where the key goes

```text
.env  or  a Codespaces secret
   │  load_dotenv() copies .env into the environment; os.getenv("GOOGLE_API_KEY") reads it
   ▼
config.load_api_key()  ──  no usable key?  ──>  MissingKeyError  ──>  "Can't start the server: ..."  (exit 1)
   │
   ▼
main.py: GOOGLE_API_KEY, a variable on the server
   ✗ never in a response     /api/status says only {"key_set": true}
   ✗ never in the page       index.html has no key in it
   ✗ never in git            .env is in .gitignore

From project 10 on, hello.py loads the key the same way and gives it to Gemini, and only to Gemini.
```

## Run it

```bash
cd tutorials/09-gemini-key
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell: .venv\Scripts\Activate.ps1
#   Windows Git Bash:   source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

With your key in `.env` (step 3) or in a Codespaces secret:

```bash
python config.py                     # GOOGLE_API_KEY is set.  (or a message saying what to do)
uvicorn main:app --reload            # the server (Ctrl+C to stop)
```

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 | `https://<codespace-name>-8000.app.github.dev` |
| Try the API by hand | http://127.0.0.1:8000/docs | `https://<codespace-name>-8000.app.github.dev/docs` |

Only one server can use port 8000 at a time: stop the previous FastAPI project's server (Ctrl+C) before starting
this one. Project 8's Streamlit app uses port 8501, so it doesn't get in the way.

The `curl` example is for bash (macOS, Linux, Codespaces, Git Bash):

```bash
curl http://127.0.0.1:8000/api/status          # {"key_set":true}
```

## Test it

The tests use fake keys only, so they pass with or without your real key, and none of them calls Gemini. There are
15 plain tests and no live ones (tests that call Gemini for real start in project 10). They check:

- where the key is read from: the `.env` file, and a key already in the environment winning over the file (2)
- that no usable key stops with a clear message: no key, only spaces, still the placeholder (3)
- that a `.env` saved as UTF-16, as Windows PowerShell 5's `echo ... > .env` does, stops with the "isn't saved as
  UTF-8 text" message (1)
- that `python config.py` with a key prints only `GOOGLE_API_KEY is set.` (1)
- that `python config.py` and `uvicorn main:app` with no key exit with code 1 and the message, not a traceback (2)
- that `/api/status` answers exactly `{"key_set": true}`, with no key in it (1)
- that the page at `/` and `/index.html` is HTML and holds no key (2), and that it checks `res.ok` (1)
- that `.env.example` ends with the placeholder line (1)
- that git ignores `.env` but not `.env.example` (1). This one is skipped when the folder isn't inside a git clone,
  for example when you downloaded the repo as a ZIP.

How they work:

- `os.environ["GOOGLE_API_KEY"] = FAKE_KEY` comes before `from main import app`, because `main` checks the key as
  soon as it's imported.
- `monkeypatch.setenv()` and `monkeypatch.delenv()` change an environment variable for one test, and put it back
  afterwards.
- `tmp_path` gives each test its own empty folder, so a test can write a `.env` of its own. Your real `.env` is never
  touched.
- `run()` starts `config.py` or uvicorn as a separate program, with `GOOGLE_API_KEY` set to whatever the test
  chooses. The no-key tests set it to `""`, which also stops your real `.env` from being used. Its `timeout=30`
  makes a test fail, rather than wait forever, if the server ever starts.
- `@pytest.mark.skipif(not in_a_git_work_tree(), reason=...)` skips the git test, instead of failing it, when git is
  missing or the folder isn't a git clone. You see an `s` instead of a dot and `1 skipped` at the end;
  `python -m pytest -rs` also prints the reason.

```bash
python -m pytest                     # all 15 tests
python -m pytest -v                  # the same, one line per test
```

### Check it by hand

With your real key set and the server running:

| Check | How | You should see |
|---|---|---|
| Not in git | The three `git` commands below | No `.env` in the list, the `.gitignore` line that ignores it, and no key found |
| Not in the page | Open the page, right-click → **View page source** | No key |
| Not on the wire | Browser DevTools → **Network** → click `status` → **Response** | Only `{"key_set":true}` |
| Fails fast | Stop the server, rename `.env` to `.env.off`, run `uvicorn main:app` (with a Codespaces secret: `GOOGLE_API_KEY= uvicorn main:app`) | The "Can't start the server" message, no traceback. Rename `.env.off` back afterwards |

```bash
git status                           # .env is not in the list: git doesn't see it
git check-ignore -v .env             # the .gitignore line that ignores it: .gitignore:10:.env  .env
git grep --untracked -nE "AIza[0-9A-Za-z_-]{35}|AQ\.[0-9A-Za-z_-]{20,}" -- :/
                                     # looks for a whole key of either kind in every file git could commit
                                     # (":/" means the whole repo, not just this folder). No output: no key found
```

## When things go wrong

| What happens | What you see | What to do |
|---|---|---|
| No `.env`, or nothing after the `=` | `Can't start the server: GOOGLE_API_KEY is not set. Copy .env.example to .env ...` | `cp .env.example .env`, then put your key after the `=` |
| `.env` still says `your-key-here` | `... GOOGLE_API_KEY is still the placeholder from .env.example: put your real key in .env.` | Replace `your-key-here` with your key |
| The file is called `.env.txt`, or it's in another folder | `GOOGLE_API_KEY is not set` | Name it exactly `.env`, in this folder, next to `config.py` |
| The variable is called `GEMINI_API_KEY` (the name in Google's own examples) | `GOOGLE_API_KEY is not set` | This repo reads only `GOOGLE_API_KEY`: rename it |
| `.env` was written by Windows PowerShell 5's `echo ... > .env`, which saves it as UTF-16 | `.env isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 encoding.` (`uvicorn main:app` shows it after `Can't start the server:`). `python -m pytest` stops too: a long `INTERNALERROR>` report whose last line ends with the same message, then `no tests ran` | Save `.env` as UTF-8 in your editor, or make it again with `cp .env.example .env` and edit that |
| A Codespaces secret was added while the codespace was running | `GOOGLE_API_KEY is not set` | Stop and restart the codespace |
| `uvicorn main:app --reload` started with no key | `Uvicorn running on http://127.0.0.1:8000`, then `Can't start the server: ...`. The page doesn't load, and creating `.env` changes nothing | Ctrl+C, fix the key, start it again |
| Another server is already using port 8000 | `error while attempting to bind on address ('127.0.0.1', 8000)` | Stop the other server (Ctrl+C) |

`GOOGLE_API_KEY is set.` only means there is a key, not that it works: this project never calls Gemini. A wrong
key, or a restriction from step 1 set the wrong way, shows up in project 10, at the first call.

## Things to try

1. **An empty variable beats `.env`.** In bash, run `GOOGLE_API_KEY= python config.py`. You get
   `GOOGLE_API_KEY is not set. ...` even though `.env` holds your key: a variable that is already set, even to
   nothing, wins over the file. (Windows PowerShell can't do this: `$env:GOOGLE_API_KEY = ""` deletes the variable,
   so `.env` is used and you get `GOOGLE_API_KEY is set.`)
2. **Leak the key on purpose, and let a test catch it.** In `main.py`, change `return {"key_set": True}` to
   `return {"key_set": True, "key": GOOGLE_API_KEY}` and run `python -m pytest`.
   `test_api_status_says_the_key_is_set_and_nothing_more` fails, and its report shows the leaked fake key:
   `{'key': 'fake-key-for-tests-123'}`. Undo the change.
3. **Warn instead of stopping, and see why that's worse.** In `main.py`, replace
   `sys.exit(f"Can't start the server: {err}")` with `print(f"Warning, no key: {err}")`. In bash, start the server
   with no key: `GOOGLE_API_KEY= uvicorn main:app`. It starts, and the page says `The server has a Gemini key`
   although there is none. `python -m pytest` now waits 30 seconds, then fails
   `test_with_no_key_it_stops_with_the_message_not_a_stack_trace` with `TimeoutExpired`: the server never stopped.
   Undo the change.

## Next

**[Project 10 · First real LLM call](../10-gemini-llm/README.md)**: the same `{name}` input as project 4, but now
Gemini writes the greeting, using this key.
