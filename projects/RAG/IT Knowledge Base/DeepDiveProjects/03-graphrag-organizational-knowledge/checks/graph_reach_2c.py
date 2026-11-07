"""Offline checks of 2C's graph side (no API key, no LLM), for the numbers on the page that check_2c.py does not cover:
  - the whole graph's size in GraphRAG's own format (every edge plus all document text), against the 32 node chunks;
  - per question, how many of the needed edges sit inside the unfiltered 2-hop subgraph from the fallback's seeds
    (figure 10's G column), and which are missing;
  - which topic-map keys occur word for word in the six questions, and which questions only the map can link.
Usage: graph_reach_2c.py REPO_DIR"""
import sys

sys.path.insert(0, sys.argv[1])
from data.mock_data import DOCUMENTS, RELATIONSHIPS  # noqa: E402
from graph_builder import (_TOPIC_MAP, build_graph, expand_subgraph, heuristic_link_entities,  # noqa: E402
                           node_display_name, serialize_subgraph)
from questions import QUESTIONS  # noqa: E402

g = build_graph()
facts = serialize_subgraph(g)
docs = sum(len(f"{d['title']}: {d['content']}") for d in DOCUMENTS)
whole = len(facts) + docs
print(f"whole graph: {len(facts)} fact chars + {docs} document chars = {whole}")

# The edges each question needs, as in vector_proxy_2c.py.
NEED = {1: [("WORKED_ON", "proj_audit_q3"), ("USED_TOOL", "proj_audit_q3")],
        2: [("DECISION_FOR", "proj_pricing"), ("APPROVED", "dec_tiered_pricing")],
        3: [("WORKED_ON", "p_bob"), ("WORKED_ON", "proj_audit_q3"), ("WORKED_ON", "proj_ml_recs"),
            ("WORKED_ON", "proj_zerotrust"), ("HAS_SKILL", "*mates")],
        4: [("ABOUT", "proj_zerotrust"), ("AUTHORED", "doc_security_policy")],
        5: [("USED_TOOL", "proj_ml_recs"), ("USED_TOOL", "proj_pricing")]}
mates = {"p_alice", "p_frank", "p_david", "p_grace"}
for i, need_spec in NEED.items():
    need = {(s, d, r) for rel, anchor in need_spec for s, d, r, _ in RELATIONSHIPS
            if r == rel and (anchor == "*mates" and s in mates or anchor in (s, d))}
    seeds = heuristic_link_entities(g, QUESTIONS[i - 1]["text"])
    sub = expand_subgraph(g, seeds, hops=2)
    have = set(sub.edges(keys=True))
    print(f"Q{i}: seeds {seeds}, needed edges {len(need)}, inside 2 hops {len(need & have)}, "
          f"subgraph {sub.number_of_nodes()} nodes ({sub.number_of_nodes() / g.number_of_nodes():.0%}), "
          f"missing {sorted(need - have)}")

texts = [q["text"].lower() for q in QUESTIONS]
in_questions = [k for k in _TOPIC_MAP if any(k in t for t in texts)]
print(f"topic-map keys found in the questions: {len(in_questions)} of {len(_TOPIC_MAP)}: {in_questions}")
names = [node_display_name(a).lower() for _, a in g.nodes(data=True)]
for i, t in enumerate(texts, 1):
    by_name = [n for n in names if n in t]
    print(f"Q{i}: whole node names in the question: {by_name or 'none (linked only by the topic map)'}")
