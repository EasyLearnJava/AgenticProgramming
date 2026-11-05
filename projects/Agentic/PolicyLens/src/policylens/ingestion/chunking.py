"""Split original section spans; keep headings as metadata without rewriting text."""

import hashlib
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from policylens.config import Settings
from policylens.grounding import body_text
from policylens.models import Chunk


def sections(text: str):
    headings, start, stack = list(re.finditer(r"(?m)^(#{1,3})[ \t]+(.+?)[ \t]*$", text)), 0, {}
    for heading in headings:
        if heading.start() > start:
            yield text[start:heading.start()], " / ".join(stack[level] for level in sorted(stack))
        level = len(heading[1])
        stack = {key: value for key, value in stack.items() if key < level}
        stack[level] = heading[2]
        start = heading.start()
    if start < len(text):
        yield text[start:], " / ".join(stack[level] for level in sorted(stack))


def chunk_documents(documents: list[Document], settings: Settings) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap, separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = []
    for doc in documents:
        meta = doc.metadata
        for section, heading in sections(doc.page_content):
            location = " · ".join(x for x in [meta.get("location", ""), heading] if x)
            for position, text in enumerate(splitter.split_text(section)):
                if not body_text(text).strip():
                    continue
                if text not in doc.page_content:
                    raise ValueError("Chunk splitter changed source text; refusing to index rewritten evidence.")
                identity = f"{meta['source_id']}|{location}|{position}|{text}"
                chunks.append(Chunk(id=hashlib.sha256(identity.encode()).hexdigest()[:20],
                    source_id=meta["source_id"], title=meta["title"], text=text,
                    location=location or "Document", url=meta.get("url"), category=meta.get("category", "Uploaded")))
    return list({chunk.id: chunk for chunk in chunks}.values())
