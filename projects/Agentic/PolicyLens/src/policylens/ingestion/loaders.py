"""Read local Markdown, TXT and text-based PDF files into LangChain Documents."""

from pathlib import Path
from io import BytesIO

from langchain_core.documents import Document
from pypdf import PdfReader

from policylens.text import clean_text

SUPPORTED = {".md", ".txt", ".pdf"}


def load_file(path: Path, metadata: dict) -> list[Document]:
    return load_bytes(path.read_bytes(), path.suffix.lower(), metadata)


def load_bytes(content: bytes, suffix: str, metadata: dict) -> list[Document]:
    """Parse the exact bytes captured for indexing, never reread a changing file."""
    if suffix not in SUPPORTED:
        raise ValueError("Supported formats: .md, .txt and text-based .pdf")
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported. Upload an unencrypted copy.")
        if len(reader.pages) > 300:
            raise ValueError("PDFs are limited to 300 pages for this local project.")
        docs = [Document(page_content=clean_text(page.extract_text() or ""),
                         metadata={**metadata, "location": f"Page {i + 1}"})
                for i, page in enumerate(reader.pages)]
        docs = [doc for doc in docs if doc.page_content]
    else:
        text = content.decode("utf-8-sig")
        docs = [Document(page_content=clean_text(text), metadata=metadata)] if text.strip() else []
    if not docs:
        raise ValueError("Document has no readable text. Scanned PDFs need OCR first.")
    return docs

