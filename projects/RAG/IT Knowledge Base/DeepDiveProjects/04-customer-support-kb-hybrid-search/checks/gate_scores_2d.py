"""Does 2D's confidence score separate answerable from unanswerable questions? Offline, no LLM.
Compares four candidate gate scores on one labelled query set (labels are ours: a query is answerable if one
knowledge-base entry states the answer):
  cosine        2D's gate: best all-MiniLM-L6-v2 cosine over the 25 documents (bot.py top_sim)
  cosine_nobrand  the same, with "CloudSync Pro"/"CloudSync" removed from queries and documents
  bm25_norm     best BM25 score with a lowercased, punctuation-stripped tokenizer, scaled to 0-1 by the set max
  rerank        best cross-encoder score (cross-encoder/ms-marco-MiniLM-L6-v2) over 2D's hybrid candidates
For each score: AUC (chance that a random answerable query outscores a random unanswerable one), the best single
threshold's accuracy, and, for cosine, how 2D's 0.35/0.55 bands split each class.
Usage: gate_scores_2d.py REPO_DIR OUT_JSON"""
import json
import os
import re
import sys
from pathlib import Path

import truststore

truststore.inject_into_ssl()
sys.path.insert(0, sys.argv[1])
import numpy as np  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402
from sentence_transformers import CrossEncoder, SentenceTransformer  # noqa: E402

from eval_set import EVAL_CASES  # noqa: E402
from knowledge_base import load_documents  # noqa: E402

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ANSWERABLE = [c.query for c in EVAL_CASES if c.expected == "answer"] + [
    "WinFsp", "SCIM bearer token", "cloudsync push --resumable", "CMEK", "TOTP seed", "501(c)(3)",
    "file.shared webhook", "MDM .msi", "Can I install it on Ubuntu?", "How do I turn on 2fa?",
    "What happens to my data if I cancel?", "How do I fix conflict copies?"]
UNANSWERABLE = [c.query for c in EVAL_CASES if c.expected == "escalate"] + [
    "Can it integrate with Salesforce?", "Is there a dark mode in the CloudSync desktop app?",
    "Can CloudSync integrate with Slack?", "Can it integrate with Slack?", "Does CloudSync support Kubernetes?",
    "What's the price of the Enterprise plan?", "Is CloudSync HIPAA compliant?", "Do you have a SOC 2 report?",
    "Can I pay with PayPal?", "Does CloudSync Pro work on Chromebooks?", "What's the weather in Paris tomorrow?"]

docs = load_documents()
texts = [d.page_content for d in docs]
brand = re.compile(r"\bcloudsync(\s+pro)?\b", re.I)
st = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
D = st.encode(texts, normalize_embeddings=True)
Dn = st.encode([brand.sub("", t) for t in texts], normalize_embeddings=True)
tok = lambda t: re.findall(r"[a-z0-9]+", t.lower())  # noqa: E731
bm25 = BM25Okapi([tok(t) for t in texts])
bm25_2d = BM25Okapi([t.split() for t in texts])  # LangChain BM25Retriever default: text.split()
BARE = {"WinFsp", "SCIM bearer token", "cloudsync push --resumable", "CMEK", "TOTP seed", "501(c)(3)",
        "file.shared webhook", "MDM .msi"}
ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2", device="cpu")


def scores(q):
    cos = D @ st.encode(q, normalize_embeddings=True)
    cosn = Dn @ st.encode(brand.sub("", q), normalize_embeddings=True)
    b = bm25.get_scores(tok(q))
    # rerank 2D's own candidate pool: BM25 top 4 with 2D's whitespace tokens + FAISS top 4 (the union bot.py sees)
    pool = sorted(set(np.argsort(-cos)[:4]) | set(np.argsort(bm25_2d.get_scores(q.split()))[::-1][:4]))  # rank_bm25 get_top_n tie order
    rr = ce.predict([(q, texts[i]) for i in pool])
    return {"cosine": float(cos.max()), "cosine_nobrand": float(cosn.max()), "bm25_raw": float(b.max()),
            "rerank": float(rr.max())}


rows = [{"query": q, "answerable": True, **scores(q)} for q in ANSWERABLE] + \
       [{"query": q, "answerable": False, **scores(q)} for q in UNANSWERABLE]
mx = max(r["bm25_raw"] for r in rows)
for r in rows:
    r["bm25_norm"] = r["bm25_raw"] / mx


def auc(key, subset=None):
    rs = subset if subset is not None else rows
    pos = [r[key] for r in rs if r["answerable"]]
    neg = [r[key] for r in rs if not r["answerable"]]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def best_threshold(key):
    vals = sorted({r[key] for r in rows})
    best = (0, None)
    for t in vals:
        acc = sum((r[key] >= t) == r["answerable"] for r in rows) / len(rows)
        best = max(best, (acc, t))
    return best


rng = np.random.default_rng(0)
pos_rows = [r for r in rows if r["answerable"]]
neg_rows = [r for r in rows if not r["answerable"]]


def boot(key, n=2000):
    vals = []
    for _ in range(n):
        sub = [pos_rows[i] for i in rng.integers(0, len(pos_rows), len(pos_rows))] +               [neg_rows[i] for i in rng.integers(0, len(neg_rows), len(neg_rows))]
        vals.append(auc(key, sub))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def boot_diff(key, n=2000):
    """Paired bootstrap: resample queries once, compare key's AUC with cosine's on the same sample."""
    vals = []
    for _ in range(n):
        sub = [pos_rows[i] for i in rng.integers(0, len(pos_rows), len(pos_rows))] +               [neg_rows[i] for i in rng.integers(0, len(neg_rows), len(neg_rows))]
        vals.append(auc(key, sub) - auc("cosine", sub))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


summary = {}
for key in ("cosine", "cosine_nobrand", "bm25_norm", "rerank"):
    acc, t = best_threshold(key)
    summary[key] = {"auc": round(auc(key), 3), "auc_95ci_bootstrap": boot(key),
                    "auc_without_bare_terms": round(auc(key, [r for r in rows if r["query"] not in BARE]), 3),
                    "best_single_threshold_accuracy": round(acc, 3), "threshold": round(t, 3)}
    if key != "cosine":
        summary[key]["auc_minus_cosine_95ci_paired"] = boot_diff(key)
bands = {}
for lab in (True, False):
    xs = [r["cosine"] for r in rows if r["answerable"] == lab]
    bands["answerable" if lab else "unanswerable"] = {
        "n": len(xs), "answer_band": sum(x >= 0.55 for x in xs), "judge_band": sum(0.35 <= x < 0.55 for x in xs),
        "escalate_band": sum(x < 0.35 for x in xs)}
Path(sys.argv[2]).write_text(json.dumps({"summary": summary, "cosine_bands": bands, "rows": rows}, indent=1),
                             encoding="utf-8")
print(json.dumps(summary, indent=1))
print(json.dumps(bands, indent=1))
for r in sorted(rows, key=lambda r: -r["cosine"]):
    print(f"{'A' if r['answerable'] else '-'} cos={r['cosine']:.3f} nobrand={r['cosine_nobrand']:.3f} "
          f"bm25={r['bm25_norm']:.2f} rerank={r['rerank']:6.2f} | {r['query']}")
