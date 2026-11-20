# 01: Load and ask

The simplest RAG app: one file loads the data, one file answers questions.

- `ingest.py` reads `data/it_kb.md` (10 IT help desk articles, one per `##` heading), cuts them into chunks, embeds each chunk with
  Gemini (`gemini-embedding-001`) and saves the vectors in a local Qdrant folder, `qdrant_data/`.
- `ask.py` embeds your question, finds the 3 closest chunks and has Gemini (`gemini-3.5-flash-lite`) answer from
  them only, then lists the articles it used.

## Run it

From this folder, in a command prompt:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

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
| My VPN keeps timing out when I work from home. What should I do? | VPN Connection Timeout |
| Which ports does the VPN need open? | VPN Connection Timeout (UDP 500 and 4500) |
| Microsoft Authenticator won't finish setting up MFA on my phone. | MFA Setup Failure (check the phone's time first) |
| My new laptop is really slow and apps freeze. | Laptop Performance Degradation |
| I get Access Denied in Salesforce since my role changed. | SaaS Access Permission Denied (allow 30 minutes) |
| The WiFi in Building C keeps dropping. | WiFi Connectivity Issues Office (SSID CorpWiFi-5G) |
| Password reset fails with error 0x80070005. | Password Reset Failed |
| What are the password rules? | Password Reset Failed (12 characters, upper, lower, number, special) |
| I can't find the HP-Floor3-Color printer after my laptop was reimaged. | Printer Not Found (IP 10.50.3.25) |
| What is the email attachment size limit? | Email Attachment Size Limit (25 MB external, 50 MB internal) |
| Our production database times out at peak hours. | Database Connection Timeout |
| I hear nothing in Teams meetings. | Microsoft Teams Audio Issues |
| How do I reset my Mac's keyboard? | Nothing: it should say it doesn't know |

## Good to know

- To change the data, edit `data/it_kb.md` (each `##` heading starts an article) and run `ingest.py` again.
- `ingest.py` embeds 20 chunks; Gemini's free tier allows 100 embedded texts a minute and 1000 a day.
- Only one program can open `qdrant_data/` at a time.
- `.env` and `qdrant_data/` are in the repo's `.gitignore`.
