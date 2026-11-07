"""Step 2 (entry-venv, sentence-transformers): embeds 2B's 12,142 fixed-size chunks with BAAI/bge-base-en-v1.5
(normalized, no query prefix, as HuggingFaceEmbeddings does) and runs the 10 test questions of cell 53 as exact cosine
search: set-up A's retrieval without Pinecone. Reports, per question, the rank of the first chunk holding the reference
figure with its row label, and which part of the submission each top-3 chunk comes from.
Usage: retrieve_fixed.py CHUNKS_JSON OUT_JSON"""
import json
import re
import sys
from pathlib import Path

import truststore

truststore.inject_into_ssl()
import numpy as np  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
chunks, parts = data["chunks"], data["parts"]
texts = [c["text"] for c in chunks]
model = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")
print("max_seq_length", model.max_seq_length, flush=True)
cache = Path(sys.argv[2]).with_suffix(".npy")
if cache.exists():
    emb = np.load(cache)
else:
    emb = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True,
                       convert_to_numpy=True)
    np.save(cache, emb)
QUESTIONS = [
    ("Q1", "What was Apple's total net revenue in fiscal year 2024?", "391,035", "Total net sales"),
    ("Q2", "What were Apple's earnings per share in 2024?", "6.11", "Basic"),
    ("Q3", "How much did Apple spend on research and development in 2024?", "31,370", "Research and development"),
    ("Q4", "What are the main risk factors related to Apple's supply chain?", None, None),
    ("Q5", "What was Apple's net income in fiscal year 2024?", "93,736", "Net income"),
    ("Q6", "What was Apple's iPhone revenue in 2024?", "201,183", "iPhone"),
    ("Q7", "What was Apple's services revenue in 2024?", "96,169", "Services"),
    ("Q8", "What was Apple's Mac revenue in fiscal year 2024?", "29,984", "Mac"),
    ("Q9", "What were Apple's Americas net sales in 2024?", "167,045", "Americas"),
    ("Q10", "What were the main factors affecting Apple's gross margin in 2024?", None, None),
]
norm = [(p["type"], re.sub(r"\s+", " ", p["text"])) for p in parts]


def source(text):
    probe = re.sub(r"\s+", " ", text.strip())[:200]
    hits = sorted({t for t, body in norm if probe in body})
    return "/".join(hits) or "?"


report = []
for qid, q, num, lab in QUESTIONS:
    qv = model.encode([q], normalize_embeddings=True, convert_to_numpy=True)[0]
    order = np.argsort(-(emb @ qv))
    first = next((r + 1 for r, i in enumerate(order[:500]) if num and num in texts[i] and lab in texts[i]), None)
    top = [{"rank": r + 1, "score": round(float(emb[i] @ qv), 3), "source": source(texts[i]),
            "has_figure": bool(num and num in texts[i]), "has_label": bool(lab and lab in texts[i]),
            "text": re.sub(r"\s+", " ", texts[i].strip())[:220]} for r, i in enumerate(order[:3])]
    report.append({"id": qid, "question": q, "figure": num, "label": lab, "first_rank_with_figure_and_label": first,
                   "top3": top})
    print(f"{qid}: first chunk with figure+label at rank {first}; top-3 sources "
          f"{[t['source'] for t in top]}; top-3 has figure {[t['has_figure'] for t in top]}", flush=True)
Path(sys.argv[2]).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
