"""Reproduces 2B's fixed-size path (cells 21, 23, 25) on the same two Apple 10-K submissions, with no embeddings,
LLM or keys, and checks whether the evaluation answers survive the is_clean_chunk filter.
Usage: fixed_filter_check.py FILINGS_DIR OUT_JSON"""
import html
import json
import re
import sys
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter


def remove_edgar_header(text):          # the solution doc's canonical version; the notebook never defines it
    marker = "UNITED STATES"
    idx = text.find(marker)
    if idx != -1:
        return text[idx:]
    return text


def clean_edgar_text(text):             # notebook cell 23, verbatim
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'ix:[^\s]+', ' ', text)
    text = re.sub(r'^[\-_=\s ]+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {3,}', ' ', text)
    return text.strip()


def is_clean_chunk(text):               # notebook cell 25, verbatim apart from taking a string
    text = text.strip()
    if len(text) < 100:
        return False
    alpha_ratio = sum(c.isalpha() for c in text) / len(text)
    if alpha_ratio < 0.4:
        return False
    return True


files = sorted(Path(sys.argv[1]).glob("*.txt"))
splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64, separators=["\n\n", "\n", ". ", " ", ""])
docs, raw = {}, []
for f in files:
    text = remove_edgar_header(clean_edgar_text(f.read_text(encoding="utf-8", errors="replace")))
    docs[f.stem] = text
    raw += [(f.stem, c) for c in splitter.split_text(text)]
kept = [(acc, c) for acc, c in raw if is_clean_chunk(c)]
report = {"files": [f.name for f in files], "cleaned_chars": {k: len(v) for k, v in docs.items()},
          "raw_chunks": len(raw), "kept_chunks": len(kept),
          "avg_kept_chars": sum(len(c) for _, c in kept) // max(1, len(kept)), "facts": {}}
facts = {"Q1 total net sales": "391,035", "Q2 basic EPS": "6.11", "Q2 diluted EPS": "6.08", "Q3 R&D": "31,370",
         "Q5 net income": "93,736", "Q6 iPhone": "201,183", "Q7 Services": "96,169", "Q8 Mac": "29,984",
         "Q9 Americas": "167,045"}
for name, needle in facts.items():
    hits_raw = [(acc, c) for acc, c in raw if needle in c]
    hits_kept = [(acc, c) for acc, c in kept if needle in c]
    report["facts"][name] = {
        "needle": needle, "in_cleaned_text": {k: v.count(needle) for k, v in docs.items()},
        "raw_chunks_with_it": len(hits_raw), "kept_chunks_with_it": len(hits_kept),
        "dropped_examples": [{"len": len(c.strip()),
                              "alpha": round(sum(ch.isalpha() for ch in c.strip()) / max(1, len(c.strip())), 2),
                              "text": c.strip()[:160]} for _, c in hits_raw if not is_clean_chunk(c)][:3],
        "kept_examples": [c.strip()[:160] for _, c in hits_kept][:2]}
Path(sys.argv[2]).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "facts"}, indent=1))
for name, f in report["facts"].items():
    print(f"{name:20} raw {f['raw_chunks_with_it']:3}  kept {f['kept_chunks_with_it']:3}")
