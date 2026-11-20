# 01: Load and ask

The simplest RAG app: one file loads the data, one file answers questions.

- `ingest.py` reads `data/it_kb.md` (10 IT help desk articles, one per `##` heading), cuts them into chunks, embeds each chunk with
  Gemini (`gemini-embedding-001`) and saves the vectors in a local Qdrant folder, `qdrant_data/`.
- `ask.py` embeds your question, finds the 3 closest chunks and has Gemini (`gemini-3.5-flash-lite`) answer from
  them only, then lists the articles it used.

## Run it

From this folder, in a command prompt:

```
python -m venv %USERPROFILE%\venvs\simple-rag
%USERPROFILE%\venvs\simple-rag\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

The venv sits in a short folder outside the repo on purpose. This project's folder is deep, and with Windows long
paths off, a `.venv` here fails to install numpy: `WinError 206: The filename or extension is too long`. In
PowerShell, activate it with `& "$env:USERPROFILE\venvs\simple-rag\Scripts\Activate.ps1"`.

Put your Gemini API key after `GOOGLE_API_KEY=` in `.env`, then:

```
python ingest.py
python ask.py "How do I fix a VPN timeout?"
```

or `python ask.py` alone to type questions one after another (an empty line quits). Run `ingest.py` once; run it
again only when the data changes.

## Questions to ask

| Question | Should come from |
| --- | --- |
| My VPN keeps timing out when I work from home. What should I do? | VPN Timeout |
| Which ports does the VPN need open? | VPN Timeout (UDP 500 and 4500) |
| Microsoft Authenticator won't finish setting up MFA on my phone. | MFA Setup (set the phone's time to automatic) |
| My laptop is really slow. | Slow Laptop |
| I get Access Denied in Salesforce since my role changed. | Salesforce Access Denied (wait 30 minutes) |
| Which WiFi network should I use? | Office WiFi (CorpWiFi-5G) |
| Password reset fails with error 0x80070005. | Password Reset |
| What are the password rules? | Password Reset (12 characters, upper, lower, number, special) |
| How do I add the HP-Floor3-Color printer? | Printer Not Found (IP 10.50.3.25) |
| What is the email attachment size limit? | Email Attachment Limit (25 MB outside, 50 MB inside) |
| Our production database times out at peak hours. | Database Timeout |
| I hear nothing in Teams meetings. | Teams Audio |
| How do I reset my Mac's keyboard? | Nothing: it should say it doesn't know |

## Good to know

- To change the data, edit `data/it_kb.md` (each `##` heading starts an article) and run `ingest.py` again.
- Each article is shorter than 500 characters, so each one is a single chunk: `ingest.py` embeds 10 chunks; Gemini's free tier allows 100 embedded texts a minute and 1000 a day.
- Only one program can open `qdrant_data/` at a time.
- `.env` and `qdrant_data/` are in the repo's `.gitignore`.
