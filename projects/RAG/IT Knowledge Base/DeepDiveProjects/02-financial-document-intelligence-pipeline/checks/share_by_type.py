"""Splits each EDGAR full submission into its <DOCUMENT>s, applies 2B's clean_edgar_text to each, and reports the
share of cleaned characters per document type. Usage: share_by_type.py FILINGS_DIR"""
import re
import sys
from collections import Counter
from pathlib import Path

src = Path(__file__).with_name("fixed_filter_check.py").read_text(encoding="utf-8")
ns = {}
exec(compile(src.split("files = sorted")[0], "ffc", "exec"), ns)
for f in sorted(Path(sys.argv[1]).glob("*.txt")):
    raw = f.read_text(encoding="utf-8", errors="replace")
    share = Counter()
    for doc in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", raw, re.S):
        kind = re.search(r"<TYPE>([^\n<]+)", doc).group(1).strip()
        share[kind if kind in ("10-K", "XML") else "other (EX-*, JSON, ZIP, GRAPHIC, …)"] += len(ns["clean_edgar_text"](doc))
    total = sum(share.values())
    print(f.stem, f"cleaned {total:,} chars:", ", ".join(f"{k} {v / total:.0%}" for k, v in share.most_common()))
