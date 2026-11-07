"""For each test fact, counts the fixed-size chunks that keep the number together with its row label, before and
after 2B's is_clean_chunk filter. Reuses fixed_filter_check.py's functions. Usage: label_check.py FILINGS_DIR"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("ffc", Path(__file__).with_name("fixed_filter_check.py"))
src = Path(__file__).with_name("fixed_filter_check.py").read_text(encoding="utf-8")
ns = {}
exec(compile(src.split("files = sorted")[0], "ffc", "exec"), ns)          # functions only, not the run
splitter = ns["RecursiveCharacterTextSplitter"](chunk_size=512, chunk_overlap=64, separators=["\n\n", "\n", ". ", " ", ""])
raw = []
for f in sorted(Path(sys.argv[1]).glob("*.txt")):
    text = ns["remove_edgar_header"](ns["clean_edgar_text"](f.read_text(encoding="utf-8", errors="replace")))
    raw += splitter.split_text(text)
facts = [("Q1 total net sales", "391,035", "Total net sales"), ("Q2 basic EPS", "6.11", "Basic"),
         ("Q3 R&D", "31,370", "Research and development"), ("Q5 net income", "93,736", "Net income"),
         ("Q6 iPhone", "201,183", "iPhone"), ("Q7 Services", "96,169", "Services"), ("Q8 Mac", "29,984", "Mac"),
         ("Q9 Americas", "167,045", "Americas")]
print(f"{'fact':20} {'number':>7} {'+label raw':>11} {'+label kept':>12}")
for name, num, lab in facts:
    both = [c for c in raw if num in c and lab in c]
    kept = [c for c in both if ns["is_clean_chunk"](c)]
    print(f"{name:20} {sum(num in c for c in raw):7} {len(both):11} {len(kept):12}")
    if kept:
        print("    e.g.", kept[0].strip()[:150].replace("\n", " "))
