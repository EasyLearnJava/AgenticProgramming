"""A fairer vector baseline for 2C, measured at retrieval level with no LLM. bge-base-en-v1.5 (local) stands in for
OpenAI's text-embedding-3-small, so absolute ranks are a proxy. Compares, for the six benchmark questions:
  A  node chunks only, top 8          (2C's baseline: 32 chunks, no relationships)
  B  node chunks + 48 edge sentences, top 8
  C  node chunks + 48 edge sentences, top 16
and reports how many gold items appear in the retrieved text, and how many of the question's required relationship
facts were retrieved. Usage: vector_proxy_2c.py REPO_DIR OUT_JSON"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, sys.argv[1])
import numpy as np  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from data.mock_data import PEOPLE, PROJECTS, SKILLS, TOOLS, DOCUMENTS, DECISIONS, RELATIONSHIPS  # noqa: E402
from questions import QUESTIONS  # noqa: E402

nodes = (
    [f"Person: {p['name']}. Role: {p['role']}. Team: {p['team']}." for p in PEOPLE]
    + [f"Project: {p['name']}. Status: {p['status']}. Started: {p['started']}. Ended: {p.get('ended') or 'ongoing'}. "
       f"Summary: {p['summary']}" for p in PROJECTS]
    + [f"Skill: {s['name']} (category: {s['category']})." for s in SKILLS]
    + [f"Tool: {t['name']} (vendor: {t['vendor']})." for t in TOOLS]
    + [f"Document: {d['title']} (type: {d['type']}). Content: {d['content']}" for d in DOCUMENTS]
    + [f"Decision: {d['title']} (date: {d['date']}). Rationale: {d['rationale']}" for d in DECISIONS])
name = {x["id"]: x.get("name") or x.get("title") for x in PEOPLE + PROJECTS + SKILLS + TOOLS + DOCUMENTS + DECISIONS}
VERB = {"WORKED_ON": "worked on", "USED_TOOL": "used the tool", "AUTHORED": "authored", "ABOUT": "is about",
        "HAS_SKILL": "has the skill", "APPROVED": "approved", "DECISION_FOR": "is a decision for"}
edges = [f"{name[s]} {VERB[r]} {name[d]}" + (f" (role: {a['role']})" if a.get("role") else "")
         for s, d, r, a in RELATIONSHIPS]
# The relationship facts each question needs (by edge), written from the graph.
NEED = {1: [("WORKED_ON", "proj_audit_q3"), ("USED_TOOL", "proj_audit_q3")],
        2: [("DECISION_FOR", "proj_pricing"), ("APPROVED", "dec_tiered_pricing")],
        3: [("WORKED_ON", "p_bob"), ("WORKED_ON", "proj_audit_q3"), ("WORKED_ON", "proj_ml_recs"),
            ("WORKED_ON", "proj_zerotrust"), ("HAS_SKILL", "*mates")],
        4: [("ABOUT", "proj_zerotrust"), ("AUTHORED", "doc_security_policy")],
        5: [("USED_TOOL", "proj_ml_recs"), ("USED_TOOL", "proj_pricing")],
        6: []}
mates = {"p_alice", "p_frank", "p_david", "p_grace"}


def needed(i):
    out = set()
    for rel, anchor in NEED[i]:
        for j, (s, d, r, a) in enumerate(RELATIONSHIPS):
            if r != rel:
                continue
            if anchor == "*mates" and s in mates or anchor in (s, d):
                out.add(j)
    return out


model = SentenceTransformer("BAAI/bge-base-en-v1.5", device="cpu")
setups = {"A node chunks, top 8": (nodes, 8), "B nodes + edge sentences, top 8": (nodes + edges, 8),
          "C nodes + edge sentences, top 16": (nodes + edges, 16)}
emb = {k: model.encode(t, normalize_embeddings=True) for k, (t, _) in setups.items() if k[0] in "AB"}
emb["C nodes + edge sentences, top 16"] = emb["B nodes + edge sentences, top 8"]
report = []
for i, q in enumerate(QUESTIONS, 1):
    qv = model.encode([q["text"]], normalize_embeddings=True)[0]
    need = needed(i)
    row = {"id": f"Q{i}", "gold": q["must_include"], "edge_facts_needed": len(need), "setups": {}}
    for k, (texts, top) in setups.items():
        order = np.argsort(-(emb[k] @ qv))[:top]
        got = [texts[j] for j in order]
        blob = " ".join(got).lower()
        edge_hits = sum(1 for j in order if j >= len(nodes) and (j - len(nodes)) in need)
        row["setups"][k] = {"gold_in_retrieved": sum(s.lower() in blob for s in q["must_include"]),
                            "edge_facts_retrieved": edge_hits, "retrieved": got}
    report.append(row)
    print(f"Q{i} (gold {len(q['must_include'])}, edge facts needed {len(need)}): " + " | ".join(
        f"{k[0]} gold {v['gold_in_retrieved']}, facts {v['edge_facts_retrieved']}" for k, v in row["setups"].items()))
Path(sys.argv[2]).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
