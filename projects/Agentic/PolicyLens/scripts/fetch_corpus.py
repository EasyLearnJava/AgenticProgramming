"""Refresh the fixed, public starter corpus. Run manually; nothing scrapes at startup.

The source URLs and SHA-256 hashes make the snapshot reproducible and auditable.
Download every page successfully before replacing any existing corpus files.
"""

import hashlib
import json
import ssl
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("spending", "Spending Company Money", "Finance",
     "https://handbook.gitlab.com/handbook/finance/spending-company-money/"),
    ("expenses", "Global Travel and Expense Policy", "Finance",
     "https://handbook.gitlab.com/handbook/finance/expenses/"),
    ("time-off", "Time Off and Absence", "People",
     "https://handbook.gitlab.com/handbook/people-group/time-off-and-absence/"),
    ("time-off-types", "Time Off Types", "People",
     "https://handbook.gitlab.com/handbook/people-group/time-off-and-absence/time-off-types/"),
    ("passwords", "Password Guidelines", "Security",
     "https://handbook.gitlab.com/handbook/security/password-guidelines/"),
    ("communication", "GitLab Communication", "Ways of working",
     "https://handbook.gitlab.com/handbook/communication/"),
]


def validate_source_url(url: str):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "handbook.gitlab.com"
            or parsed.username or parsed.password or parsed.port not in {None, 443}):
        raise ValueError("Source URLs and redirect targets must use HTTPS on handbook.gitlab.com.")


def fetch_page(client, url: str):
    for _ in range(6):
        validate_source_url(url)  # Validate BEFORE every request, including redirects.
        response = client.get(url)
        if response.is_redirect:
            target = response.headers.get("location")
            if not target:
                raise ValueError("Redirect is missing its target.")
            url = urljoin(url, target)
            continue
        response.raise_for_status()
        return response
    raise ValueError("Too many source redirects.")


def extract_content(html: str, title: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one(".td-content") or soup.find("article") or soup.find("main")
    if article is None:
        raise ValueError("No main article found; refusing to ingest navigation as policy.")
    for node in article.select("script, style, nav, footer, .td-page-meta, .feedback--prompt, .feedback--answer"):
        node.decompose()
    lines = []
    blocks = {"div", "section", "p", "li", "ul", "ol", "blockquote", "table", "pre",
              "h1", "h2", "h3", "h4", "h5", "h6", "dl", "dt", "dd"}

    def walk(node):
        if node.name == "table":
            # A row may contain <p> and nested markup; emit its cells exactly once.
            for row in node.find_all("tr"):
                if row.find_parent("table") is node:
                    cells = row.find_all(["th", "td"], recursive=False)
                    lines.append(" | ".join(" ".join(cell.get_text(" ", strip=True).split()) for cell in cells))
            return
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            lines.append("#" * min(int(node.name[1]), 3) + " " + " ".join(node.get_text(" ", strip=True).split()))
            return
        inline = []

        def flush():
            text = " ".join(" ".join(inline).split())
            if text:
                lines.append(text)
            inline.clear()

        for child in node.children:
            if isinstance(child, NavigableString):
                inline.append(str(child))
            elif child.name in blocks or child.find(list(blocks)):
                flush()
                walk(child)
            else:
                inline.append(child.get_text(" ", strip=True))
        flush()

    walk(article)
    text = "\n\n".join(lines)
    if len(text) < 300:
        raise ValueError(f"{title} returned too little article text.")
    return text + "\n"


def main():
    folder = ROOT / "data" / "corpus"
    folder.mkdir(parents=True, exist_ok=True)
    downloaded, manifest = {}, []
    now = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=45, follow_redirects=False, verify=ssl.create_default_context(),
                      headers={"User-Agent": "PolicyLens-Educational-RAG/1.0"}) as client:
        for source_id, title, category, url in SOURCES:
            response = fetch_page(client, url)
            text = extract_content(response.text, title)
            filename = f"{source_id}.md"
            # Hash and write the SAME bytes; Path.write_text otherwise expands LF on Windows.
            content = text.encode("utf-8")
            downloaded[filename] = content
            manifest.append({"source_id": source_id, "title": title, "category": category,
                             "url": str(response.url), "file": filename, "fetched_at": now,
                             "sha256": hashlib.sha256(content).hexdigest(),
                             "owner": "GitLab", "license": "MIT"})
            print(f"Fetched {title}: {len(text):,} characters")
    for filename, content in downloaded.items():
        temporary = folder / (filename + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(folder / filename)
    temporary = folder / "sources.json.tmp"
    temporary.write_bytes(json.dumps(manifest, indent=2).encode("utf-8"))
    temporary.replace(folder / "sources.json")
    print("Snapshot refreshed. Rebuild the index in the app to apply it.")


if __name__ == "__main__":
    main()

