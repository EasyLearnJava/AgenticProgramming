"""Chunks each <DOCUMENT> of the two submissions separately with 2B's fixed-size splitter and filter, and counts
kept chunks by document type: an estimate of where the 12,142 indexed chunks come from.
Usage: chunks_by_type.py FILINGS_DIR"""
import re
import sys
from collections import Counter
from pathlib import Path

src = Path(__file__).with_name("fixed_filter_check.py").read_text(encoding="utf-8")
ns = {}
exec(compile(src.split("files = sorted")[0], "ffc", "exec"), ns)
splitter = ns["RecursiveCharacterTextSplitter"](chunk_size=512, chunk_overlap=64, separators=["\n\n", "\n", ". ", " ", ""])
kept, chars, example = Counter(), Counter(), {}
for f in sorted(Path(sys.argv[1]).glob("*.txt")):
    for doc in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", f.read_text(encoding="utf-8", errors="replace"), re.S):
        kind = re.search(r"<TYPE>([^\n<]+)", doc).group(1).strip()
        kind = kind if kind in ("10-K", "XML", "JSON", "ZIP", "GRAPHIC", "EXCEL") else (
            "EX-101 (XBRL)" if kind.startswith("EX-101") else "EX-other")
        text = ns["clean_edgar_text"](doc)
        chars[kind] += len(text)
        for c in splitter.split_text(text):
            if ns["is_clean_chunk"](c):
                kept[kind] += 1
                example.setdefault(kind, c.strip()[:90].replace("\n", " "))
total = sum(kept.values())
print(f"kept chunks (estimate) {total:,}")
for k, n in kept.most_common():
    print(f"  {k:14} {n:6,} chunks {n / total:5.0%}   cleaned chars {chars[k]:>9,}   e.g. {example[k]!r}")
