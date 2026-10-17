# 09 · Get a Gemini key and keep it secret

Before the first model call: create an API key, cap what it can spend, and keep it where the browser can never see
it. The server reads the key when it starts and refuses to start without one. No model call yet: that's project 10.

```text
python config.py         ->  GOOGLE_API_KEY is set.
GET /api/status          ->  {"key_set": true}               (never the key itself)
no key at start-up       ->  Can't start the server: GOOGLE_API_KEY is not set. Copy .env.example to .env ...
```

## What you learn

- **An API key** is a password for your account: whoever has it can call the model, and you pay for it
- **Environment variables**, and **`python-dotenv`** to load them from a `.env` file
- **The key stays on the server**: the page asks the server, and the server asks Gemini
- **A fail-fast check**: stop at start-up with a clear message, not later with a confusing error

## 1. Create the key

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

## 2. Cap the spend, before the first call

- **Budget alert:** in the Google Cloud console, for the key's project, go to **Billing → Budgets & alerts** and set
  a small budget, for example $5, with email alerts.
- **Quota (optional, a hard limit):** in **APIs & Services → Gemini API → Quotas**, lower the
  requests per minute or per day.

A budget alert only warns you, while a quota actually stops the calls. Every project from here on also sets
`max_output_tokens` on each call.

## 3. Put the key where only the server can read it

Pick **one** of these:

**A `.env` file** (on your laptop, or in Codespaces):
```bash
cd projects/09-gemini-key
cp .env.example .env               # then open .env and replace your-key-here with your key
```
`.env` is in the repo's `.gitignore`, so git never sees it. `.env.example` is committed, so it must only ever hold
the placeholder.

**A Codespaces secret** (keeps the key out of every file): on GitHub go to **Settings → Codespaces → Secrets → New
secret**, name it `GOOGLE_API_KEY`, and give it access to this repository. Then rebuild the codespace (or stop and
start it): a running codespace doesn't see a new secret.

In production, the same variable goes in the hosting provider's environment variables.

**Never** paste the key into the code, the page, a commit, a screenshot or a chat with an AI assistant. If it leaks,
rotate it (or delete it) on the Credentials page and use the new one.

## Files

| File | What it is |
|---|---|
| `config.py` | `load_api_key()`: loads `.env`, reads `GOOGLE_API_KEY`, and raises `MissingKeyError` with a clear message if it's missing or still the placeholder. `python config.py` checks it from the terminal |
| `main.py` | FastAPI: checks the key when it starts (no key, no server), serves the page, and `GET /api/status` says `{"key_set": true}` |
| `index.html` | The page: asks `/api/status` when it opens and shows the answer |
| `.env.example` | The template: `GOOGLE_API_KEY=your-key-here`. Copy it to `.env` |
| `tests/test_config.py` | Tests where the key is read from, the clear errors, that the server won't start without a key, that no response or page holds the key, and that git ignores `.env`. All with fake keys |
| `requirements.txt` | `fastapi`, `uvicorn`, `python-dotenv` |
| `requirements-dev.txt` | Adds `pytest` and `httpx` for the tests |

## Where the key goes

```text
.env  or  a Codespaces secret
   │  load_dotenv() copies .env into the environment; os.getenv("GOOGLE_API_KEY") reads it
   ▼
config.load_api_key()  ──  missing?  ──>  MissingKeyError  ──>  "Can't start the server: ..."  (exit, no traceback)
   │
   ▼
main.py: GOOGLE_API_KEY, a variable on the server  ──  project 10 sends it to Gemini, and only to Gemini
   ✗ never in a response     /api/status says only {"key_set": true}
   ✗ never in the page       index.html has no key in it
   ✗ never in git            .env is in .gitignore
```

If the key is set in both places, the environment wins: `load_dotenv()` never overwrites a variable that is already
set. So a Codespaces secret beats a `.env` file.

## Check it yourself

With your real key set and the server running:

| Check | How | You should see |
|---|---|---|
| Not in git | `git status`, then `git grep -nE "AIza[0-9A-Za-z_-]{35}|AQ\.[0-9A-Za-z_-]{20,}"` (a whole key of either kind) | No `.env` in the list, and no matches |
| Ignored by git | `git check-ignore -v projects/09-gemini-key/.env` | The `.gitignore` line that ignores it |
| Not in the page | Open the page, right-click → **View page source** | No key |
| Not on the wire | Browser DevTools → **Network** → click `status` → **Response** | Only `{"key_set":true}` |
| Fails fast | Rename `.env` to `.env.off`, run `uvicorn main:app` | The "Can't start the server" message, no traceback |

## Run it

```bash
cd projects/09-gemini-key
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # once: then open .env and replace your-key-here with your key
                                   # (skip this if you use a Codespaces secret instead; see step 3)
python config.py                   # GOOGLE_API_KEY is set.  (or a message saying what to do)
python -m pytest                   # 13 tests; they use fake keys, so they pass with or without your real one

uvicorn main:app --reload          # the server (Ctrl+C to stop)
```

With `--reload` and no key, the server prints the message but the reloader keeps waiting. Adding `.env` doesn't
restart it, because it only watches `.py` files. Press Ctrl+C and start it again.

With the server running, open:

| What | On your laptop | In GitHub Codespaces |
|---|---|---|
| The page | http://127.0.0.1:8000 or `/index.html` | `https://<codespace-name>-8000.app.github.dev` or `/index.html` |
| The status | http://127.0.0.1:8000/api/status | `https://<codespace-name>-8000.app.github.dev/api/status` |

Only one server can use port 8000: stop the previous project's server (Ctrl+C) before starting this one.

## Next

Project 10 makes the first real call: the same kind of prompt, but Gemini writes the answer, using this key.
