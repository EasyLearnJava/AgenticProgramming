"""Step 1 (py2b venv): writes 2B's exact fixed-size kept chunks (cells 21-25, with the solution kit's header removal)
and each <DOCUMENT>'s cleaned text, for the retrieval check in step 2. Usage: dump_fixed_chunks.py FILINGS_DIR OUT_JSON"""
import json
import re
import sys
from pathlib import Path

src = Path(__file__).with_name("fixed_filter_check.py").read_text(encoding="utf-8")
ns = {}
exec(compile(src.split("files = sorted")[0], "ffc", "exec"), ns)
splitter = ns["RecursiveCharacterTextSplitter"](chunk_size=512, chunk_overlap=64, separators=["\n\n", "\n", ". ", " ", ""])
chunks, parts = [], []
for f in sorted(Path(sys.argv[1]).glob("*.txt")):
    raw = f.read_text(encoding="utf-8", errors="replace")
    text = ns["remove_edgar_header"](ns["clean_edgar_text"](raw))
    chunks += [{"filing": f.stem, "text": c} for c in splitter.split_text(text) if ns["is_clean_chunk"](c)]
    for doc in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", raw, re.S):
        kind = re.search(r"<TYPE>([^\n<]+)", doc).group(1).strip()
        parts.append({"filing": f.stem, "type": kind, "text": ns["clean_edgar_text"](doc)})
Path(sys.argv[2]).write_text(json.dumps({"chunks": chunks, "parts": parts}, ensure_ascii=False), encoding="utf-8")
print(len(chunks), "kept chunks,", len(parts), "documents")
