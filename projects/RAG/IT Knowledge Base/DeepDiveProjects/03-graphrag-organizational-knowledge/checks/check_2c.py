"""Offline checks of 2C (no API key, no LLM): what each pipeline can possibly see for the six benchmark questions.
Imports 2C's own graph_builder and mock data (reviewed: plain Python, no network), rebuilds the vector chunks with the
format strings of vector_rag.py, and reports per question:
  - vector side: whether each gold item appears in any of the 32 chunks, and whether any chunk links it to the
    question's anchor (the relationship stated as text);
  - graph side: heuristic-linker seeds, the 2-hop subgraph with no filter and with the relation filter an LLM would
    most likely pick, its share of the graph, its size as text, and gold coverage;
  - the fuzzy matcher's collisions, gold-set substring collisions, and Q3's full answer from the graph.
Usage: check_2c.py REPO_DIR OUT_JSON"""
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from data.mock_data import PEOPLE, PROJECTS, SKILLS, TOOLS, DOCUMENTS, DECISIONS  # noqa: E402
from graph_builder import (build_graph, heuristic_link_entities, expand_subgraph, serialize_subgraph,  # noqa: E402
                           _fuzzy_match, node_display_name)
from questions import QUESTIONS  # noqa: E402

g = build_graph()
chunks = (
    [f"Person: {p['name']}. Role: {p['role']}. Team: {p['team']}." for p in PEOPLE]
    + [f"Project: {p['name']}. Status: {p['status']}. Started: {p['started']}. Ended: {p.get('ended') or 'ongoing'}. "
       f"Summary: {p['summary']}" for p in PROJECTS]
    + [f"Skill: {s['name']} (category: {s['category']})." for s in SKILLS]
    + [f"Tool: {t['name']} (vendor: {t['vendor']})." for t in TOOLS]
    + [f"Document: {d['title']} (type: {d['type']}). Content: {d['content']}" for d in DOCUMENTS]
    + [f"Decision: {d['title']} (date: {d['date']}). Rationale: {d['rationale']}" for d in DECISIONS])
low = [c.lower() for c in chunks]
ANCHORS = {1: ["soc2", "compliance audit"], 2: ["pricing"], 3: ["bob martinez"], 4: ["zero-trust", "zero trust"],
           5: ["ml recommendation engine", "pricing model redesign"], 6: ["soc2 audit"]}
FILTERS = {1: ["WORKED_ON", "USED_TOOL"], 2: ["DECISION_FOR", "APPROVED"], 3: ["WORKED_ON", "HAS_SKILL"],
           4: ["AUTHORED", "ABOUT"], 5: ["USED_TOOL"], 6: None}
docs_by_id = {d["id"]: d for d in DOCUMENTS}


def context(sub):
    facts = serialize_subgraph(sub)
    snippets = [f"{docs_by_id[n]['title']}: {docs_by_id[n]['content']}" for n, a in sub.nodes(data=True)
                if a.get("kind") == "Document" and n in docs_by_id]
    return facts, snippets


report = {"nodes": g.number_of_nodes(), "edges": g.number_of_edges(), "chunks": len(chunks),
          "all_chunks_chars": sum(len(c) for c in chunks), "questions": []}
for i, q in enumerate(QUESTIONS, 1):
    gold = q["must_include"]
    anchors = ANCHORS[i]
    seeds = heuristic_link_entities(g, q["text"])
    row = {"id": f"Q{i}", "question": q["text"], "gold": gold, "heuristic_seeds": seeds,
           "vector_any_chunk": {s: any(s.lower() in c for c in low) for s in gold},
           "vector_linked_to_anchor": {s: any(s.lower() in c and any(a in c for a in anchors) for c in low)
                                       for s in gold}}
    for label, filt in (("no_filter", None), ("likely_filter", FILTERS[i])):
        sub = expand_subgraph(g, seeds, hops=2, relation_filter=filt)
        if filt and sub.number_of_edges() == 0:
            sub = expand_subgraph(g, seeds, hops=2, relation_filter=None)
        facts, snippets = context(sub)
        text = (facts + "\n" + "\n".join(snippets)).lower()
        row[label] = {"filter": filt, "nodes": sub.number_of_nodes(), "edges": sub.number_of_edges(),
                      "share_of_nodes": round(sub.number_of_nodes() / g.number_of_nodes(), 2),
                      "chars": len(facts) + sum(len(s) for s in snippets),
                      "gold_in_context": {s: s.lower() in text for s in gold}}
    report["questions"].append(row)

cands = [(n, node_display_name(a)) for n, a in g.nodes(data=True)]
report["fuzzy_self_test"] = [{"label": lab, "expected": nid, "got": _fuzzy_match(lab, cands)}
                             for nid, lab in cands if _fuzzy_match(lab, cands) != nid]
report["fuzzy_probes"] = {p: _fuzzy_match(p, cands) for p in
                          ["AWS Audit Manager", "AWS", "SOC2", "audit", "Okta", "Drata", "zero-trust", "pricing model",
                           "Bob", "Information Security Policy", "Snowflake", "ML", "MFA"]}
names = [lab for _, lab in cands]
report["gold_collisions"] = {s: [n for n in names if s.lower() in n.lower() and n.lower() != s.lower()]
                             for q in QUESTIONS for s in q["must_include"]
                             if any(s.lower() in n.lower() and n.lower() != s.lower() for n in names)}
bob_projects = sorted({d for _, d, k in g.out_edges("p_bob", keys=True) if k == "WORKED_ON"})
mates = sorted({s for p in bob_projects for s, _, k in g.in_edges(p, keys=True) if k == "WORKED_ON"} - {"p_bob"})
mate_skills = sorted({node_display_name(g.nodes[d]) for m in mates for _, d, k in g.out_edges(m, keys=True)
                      if k == "HAS_SKILL"})
report["q3_from_graph"] = {"projects": [node_display_name(g.nodes[p]) for p in bob_projects],
                           "teammates": [node_display_name(g.nodes[m]) for m in mates], "teammate_skills": mate_skills}
Path(sys.argv[2]).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "questions"}, indent=1, ensure_ascii=False))
for r in report["questions"]:
    print(f"\n{r['id']}: seeds {r['heuristic_seeds']}")
    print("   vector: gold in any chunk", sum(r["vector_any_chunk"].values()), "/", len(r["gold"]),
          "| linked to anchor", [s for s, v in r["vector_linked_to_anchor"].items() if v])
    for label in ("no_filter", "likely_filter"):
        x = r[label]
        print(f"   graph {label:13} filter={x['filter']} nodes={x['nodes']} ({x['share_of_nodes']:.0%}) "
              f"edges={x['edges']} chars={x['chars']} gold={sum(x['gold_in_context'].values())}/{len(r['gold'])}")
