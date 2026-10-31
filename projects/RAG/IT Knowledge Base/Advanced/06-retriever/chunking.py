"""
IT Knowledge Base: Chunking
===========================

Cuts each article's Document into chunks for search: along its sections first, then by size, measured in tokens.
It handles:
  1. KBTextSplitter: a LangChain TextSplitter that never lets a chunk cross from one section (Problem, Resolution,
     Notes) into another, and packs each section's sentences into chunks of at most chunk_size tokens
  2. A header on every chunk: its article's title and its section, so "Restart the service" still says which one
  3. Each chunk's identity: chunk_id (from its article, section and text, so the same text gets the same ID on every
     run), its section, position and token count, and its parent: the whole section, kept in splitter.parents
  4. Checks: a repeated paragraph removed, a fragment merged into the chunk before it, a piece with no spaces cut to
     size; each one in splitter.report, with why

    KBTextSplitter(chunk_size=128).split_documents(docs)  ->  chunks, each with chunk_id, section, position, ...
"""
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

from utils import count_tokens, short_hash, simplify

# The sizes, in tokens: kb_settings.toml's [chunking] can change each one
CHUNK_SIZE = 128        # a chunk's size, its header included
CHUNK_OVERLAP = 16      # the last sentences of a chunk, up to this many tokens, start the next one
MIN_TOKENS = 8          # a smaller piece is merged into the chunk before it
MAX_TOKENS = 512        # the ceiling no chunk ever passes: well under gemini-embedding-001's 2,048

# A Document's text is "Title: ...\n\nProblem: ...\n\nResolution: ...\n\nNotes: ..." (Advanced/02): its title goes
# into every chunk's header, and each other section is cut on its own
TITLE = "Title"
SECTIONS = ("Problem", "Resolution", "Notes")

# A sentence ends at ".", "!" or "?" and a space, unless the stop follows a digit: "1. Verify" is one step, not two
SENTENCE_END = re.compile(r"(?<=[^\d\s][.!?])\s+")

# A paragraph shown in the report, up to this many characters
SHOW_LIMIT = 50


# -------------------------------------------------
# ChunkReport - Everything Removed, Merged or Cut Again
# -------------------------------------------------

@dataclass
class ChunkIssue:
    """One thing the checks did while cutting an article: where, and what."""
    doc_id: str
    title: str
    section: str
    message: str


@dataclass
class ChunkReport:
    """What split_documents() did: how many articles and chunks, and every piece removed, merged or cut again."""
    articles: int = 0
    chunks: int = 0
    removed: list[ChunkIssue] = field(default_factory=list)   # a paragraph already earlier in the article
    merged: list[ChunkIssue] = field(default_factory=list)    # a fragment, joined to the chunk before it
    cut: list[ChunkIssue] = field(default_factory=list)       # a piece with no spaces, cut to fit

    def has_issues(self) -> bool:
        return bool(self.removed or self.merged or self.cut)


# -------------------------------------------------
# KBTextSplitter Class - Cuts Articles Into Chunks
# -------------------------------------------------

class KBTextSplitter(TextSplitter):
    """
    A LangChain text splitter for the knowledge base's Documents.

    Step 1: Configure: the constructor stores the sizes and how to count tokens
    Step 2: Split: split_documents(), inherited from TextSplitter, gives the chunks; afterwards self.parents holds
            each section whole, and self.report what was removed, merged or cut again, and why
    """

    def __init__(self, *, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP,
                 min_tokens: int = MIN_TOKENS, max_tokens: int = MAX_TOKENS,
                 length_function: Callable[[str], int] = count_tokens, sections: tuple[str, ...] = SECTIONS):
        """
        Args:
            chunk_size: a chunk's size in tokens, its header included
            chunk_overlap: how many tokens of whole sentences a chunk may repeat from the one before it
            min_tokens: a piece smaller than this is merged into the chunk before it, in the same section
            max_tokens: the ceiling no chunk passes (a merged fragment can take a chunk past chunk_size, not this)
            length_function: counts a text's tokens (default: count_tokens(), an estimate that errs high)
            sections: the labels of the sections each cut on its own, in a Document's text
        """
        if not 0 < min_tokens < chunk_size or not 0 <= chunk_overlap < chunk_size \
                or chunk_size + min_tokens > max_tokens:
            raise ValueError(f"The sizes must keep chunk_overlap ({chunk_overlap}) and min_tokens ({min_tokens}) "
                             f"below chunk_size ({chunk_size}), and chunk_size + min_tokens <= max_tokens "
                             f"({max_tokens})")
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=length_function)
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.sections = tuple(sections)
        self._section_start = re.compile(r"(?:^|\n\n)(" + "|".join(map(re.escape, (TITLE, *self.sections))) + "): ")
        self.report = ChunkReport()
        self.parents: dict[str, Document] = {}

    def split_text(self, text: str) -> list[str]:
        """One Document's text as its chunks' texts, each with its header (the report and parents aren't kept)."""
        return [header + body for _, header, body in self._cut_article(text, "", ChunkReport())]

    def create_documents(self, texts: list[str], metadatas: list[dict] | None = None) -> list[Document]:
        """
        One Document per chunk: its article's metadata, and its own chunk_id, section, position, token_count and
        parent_id. split_documents() calls this; each call starts a new report and new parents.
        """
        self.report = report = ChunkReport()
        self.parents = {}
        chunks = []
        for index, text in enumerate(texts):
            metadata = dict(metadatas[index]) if metadatas else {}
            doc_id = str(metadata.get("doc_id", index))
            report.articles += 1
            for position, (section, header, body) in enumerate(self._cut_article(text, doc_id, report)):
                parent_id = f"{doc_id}:{section}"
                chunks.append(Document(page_content=header + body, metadata={
                    **metadata, "chunk_id": f"{parent_id}:{short_hash(body)[:8]}", "section": section,
                    "position": position, "token_count": self._length_function(header + body),
                    "parent_id": parent_id}))
        report.chunks = len(chunks)
        return chunks

    def _cut_article(self, text: str, doc_id: str, report: ChunkReport) -> Iterable[tuple[str, str, str]]:
        """(section, header, body) for each chunk of one article, in order. Each section's whole text is kept in
        self.parents, as the parent of its chunks."""
        title, sections = self._sections(text)
        seen: dict[str, str] = {}                      # a paragraph, simplified -> the section it was first in
        chunked: set[str] = set()                      # each chunk's text, simplified: no two alike in an article
        for section, body in sections:
            header = f"{title}\n{section.capitalize()}: " if title else f"{section.capitalize()}: "

            def note(found: list[ChunkIssue], message: str, section: str = section) -> None:
                found.append(ChunkIssue(doc_id, title, section, message))

            # A paragraph already earlier in the article is removed (the first copy is kept)
            kept = []
            for paragraph in (part.strip() for part in body.split("\n\n")):
                key = simplify(paragraph)
                if not key:
                    continue
                if key in seen:
                    shown = paragraph if len(paragraph) <= SHOW_LIMIT else paragraph[:SHOW_LIMIT - 3] + "..."
                    note(report.removed, f'a paragraph already in {seen[key]}: "{shown}"')
                    continue
                seen[key] = section
                kept.append(paragraph)
            if not kept:
                continue
            self.parents[f"{doc_id}:{section}"] = Document(page_content=header + "\n\n".join(kept),
                                                           metadata={"parent_id": f"{doc_id}:{section}",
                                                                     "doc_id": doc_id, "section": section})
            for piece in self._pack(kept, header, note, report):
                if simplify(piece) in chunked:         # cut from a repeating run, say: the copy adds nothing
                    note(report.removed, "a chunk the same as one before it")
                    continue
                chunked.add(simplify(piece))
                yield section, header, piece

    def _sections(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """The title, and each other section as (its name in lower case, its text). Text before the first label
        (a Document from another source, say) is one section, "text"."""
        parts = self._section_start.split(text)
        sections = [("text", parts[0])] if parts[0].strip() else []
        title = ""
        for label, body in zip(parts[1::2], parts[2::2], strict=True):
            if label == TITLE:
                title = " ".join(body.split())
            else:
                sections.append((label.lower(), body))
        return title, sections

    def _pack(self, paragraphs: list[str], header: str, note: Callable, report: ChunkReport) -> list[str]:
        """A section's sentences packed into chunks of at most chunk_size tokens with the header, never cutting a
        sentence for overlap; then a last fragment merged into the chunk before it."""
        budget = self._chunk_size - self._length_function(header)
        pieces = []
        for paragraph in paragraphs:
            for sentence in SENTENCE_END.split(paragraph):
                if self._length_function(sentence) <= budget:
                    pieces.append(sentence)
                    continue
                for word in sentence.split():           # a sentence longer than a chunk: by words
                    pieces.extend(self._cut_word(word, budget, note, report))

        chunks: list[list[str]] = []
        current: list[str] = []
        size = fresh = 0                                # fresh: pieces in current that aren't overlap
        for piece in pieces:
            tokens = self._length_function(piece)
            if fresh and size + tokens > budget:
                chunks.append(current)
                overlap: list[str] = []                 # whole sentences from the end, up to chunk_overlap tokens
                for previous in reversed(current):
                    if sum(map(self._length_function, [previous, *overlap])) > self._chunk_overlap:
                        break
                    overlap.insert(0, previous)
                current, size, fresh = overlap, sum(map(self._length_function, overlap)), 0
            if size + tokens > budget:                  # the overlap and this piece don't fit together: no overlap
                current, size = [], 0
            current.append(piece)
            size += tokens
            fresh += 1
        if fresh:
            chunks.append(current)

        texts = [" ".join(chunk) for chunk in chunks]
        if len(texts) > 1 and self._length_function(texts[-1]) < self.min_tokens:
            last = texts.pop()
            note(report.merged, f"a {self._length_function(last)}-token piece merged into the chunk before it")
            texts[-1] = f"{texts[-1]} {last}"
        return texts

    def _cut_word(self, word: str, budget: int, note: Callable, report: ChunkReport) -> list[str]:
        """A word, or a longer run with no spaces (a log line, a key), as pieces of at most budget tokens."""
        if self._length_function(word) <= budget:
            return [word]
        pieces, rest = [], word
        while rest:
            end = len(rest)
            while self._length_function(rest[:end]) > budget:
                end = max(1, end * budget // self._length_function(rest[:end]))
            pieces.append(rest[:end])
            rest = rest[end:]
        note(report.cut, f"a {self._length_function(word)}-token piece with no spaces cut into {len(pieces)} pieces")
        return pieces
