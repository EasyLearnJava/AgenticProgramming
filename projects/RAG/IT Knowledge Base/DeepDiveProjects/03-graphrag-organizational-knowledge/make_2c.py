"""Writes the requirement, FDE analysis and architecture page of The Gen Academy's 2C GraphRAG for
Organizational Knowledge as one self-contained HTML file. Reads Parts 1 and 2 from fde_2c.html beside it.
Usage: make_2b.py OUT_HTML. Warns when a line is likely too long for its box."""
import re
import sys
from html import escape
from pathlib import Path

OUT = Path(sys.argv[1])
CHAR = {"t": 7.6, "s": 6.5, "m": 6.3, "pm": 7.2, "msg": 6.6}
out, warnings = [], []
P = ""


def text(x, y, s, cls, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>')


def fits(s, width, cls, where):
    if len(s) * CHAR.get(cls, 6.5) > width:
        warnings.append(f"{where}: {len(s)} chars may overflow {width}px: {s}")


def box(x, y, w, h, title, lines=(), cls="bx", tag=None, warn=(), lcls="s", step=16):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" class="{cls}"/>')
    text(x + 12, y + 22, title, "t")
    fits(title, w - 24, "t", title)
    for i, line in enumerate(lines):
        text(x + 12, y + 42 + step * i, line, lcls)
        fits(line, w - 24, lcls, title)
    if tag:
        text(x + w - 12, y + h - 10, tag, "tag", "end")
    for i, n in enumerate(warn):
        dot(x + w - 16 - 24 * i, y + 16, n)


def dot(cx, cy, n):
    out.append(f'<circle cx="{cx}" cy="{cy}" r="9.5" class="wb"/>')
    text(cx, cy + 4, str(n), "wbt", "middle")


def label(x, y, s, anchor="start", cls="lbl"):
    text(x, y, s, cls, anchor)


def header(x, y, s, sub=None):
    text(x, y, s, "h")
    if sub:
        text(x, y + 18, sub, "hs")


def person(cx, top, name, sub):
    out.append(f'<circle cx="{cx}" cy="{top + 14}" r="13" class="pa"/>')
    out.append(f'<path d="M{cx - 24} {top + 62} Q{cx - 24} {top + 32} {cx} {top + 32} '
               f'Q{cx + 24} {top + 32} {cx + 24} {top + 62} Z" class="pa"/>')
    text(cx, top + 82, name, "t", "middle")
    text(cx, top + 99, sub, "s", "middle")


def defs(p):
    m = ('<marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
         'orient="{o}"><path d="M0,0 L10,5 L0,10 z" class="{c}"/></marker>')
    return ("<defs>" + m.format(id=p + "ar", c="ah", o="auto") + m.format(id=p + "arc", c="ahc", o="auto")
            + m.format(id=p + "arr", c="ahr", o="auto") + m.format(id=p + "arb", c="ah", o="auto-start-reverse")
            + m.format(id=p + "arrb", c="ahr", o="auto-start-reverse")
            + f'<marker id="{p}aro" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
              f'orient="auto"><path d="M0,0 L10,5 L0,10" class="aho"/></marker></defs>')


def fl(d, kind="ln"):
    if kind in ("both", "bothr"):
        mk, cls = ("arb", "ln") if kind == "both" else ("arrb", "lnr")
        out.append(f'<path d="{d}" class="{cls}" marker-start="url(#{P}{mk})" marker-end="url(#{P}{mk})"/>')
        return
    mk = {"ln": "ar", "lnd": "ar", "ret": "aro", "lnc": "arc", "lnr": "arr"}[kind]
    out.append(f'<path d="{d}" class="{kind}" marker-end="url(#{P}{mk})"/>')


def proc(x, y, w, h, pid, title, lines=()):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" class="pr"/>')
    out.append(f'<path d="M{x} {y + 24} H{x + w}" class="prl"/>')
    text(x + w / 2, y + 17, pid, "pid", "middle")
    text(x + w / 2, y + 43, title, "t2", "middle")
    fits(title, w - 12, "t", title)
    for i, line in enumerate(lines):
        text(x + w / 2, y + 60 + 14 * i, line, "m", "middle")
        fits(line, w - 10, "m", title)


def store(x, y, w, h, sid, title, lines=()):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="dsf"/>')
    out.append(f'<path d="M{x + w} {y} H{x} V{y + h} H{x + w} M{x + 44} {y} V{y + h}" class="dsl"/>')
    text(x + 22, y + h / 2 + 5, sid, "dsid", "middle")
    text(x + 54, y + 19, title, "t2")
    fits(title, w - 60, "t", title)
    for i, line in enumerate(lines):
        text(x + 54, y + 35 + 14 * i, line, "m")
        fits(line, w - 60, "m", title)


def ent(x, y, w, h, eid, title, sub=""):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="ee"/>')
    text(x + w / 2, y + (h / 2 - 3 if sub else h / 2 + 5), f"{eid} · {title}", "t2", "middle")
    if sub:
        text(x + w / 2, y + h / 2 + 14, sub, "m", "middle")
        fits(sub, w - 10, "m", title)


def card(x, y, w, title, rows, kw, sub=None, cls="bx"):
    h = 34 + (16 if sub else 0) + 17 * len(rows) + 8
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" class="{cls}"/>')
    text(x + 12, y + 22, title, "t2")
    fits(title, w - 24, "t", title)
    y0 = y + 42
    if sub:
        text(x + 12, y + 40, sub, "m")
        fits(sub, w - 24, "m", title)
        y0 += 16
    for i, (k, v) in enumerate(rows):
        text(x + 12, y0 + 17 * i, k, "mf")
        text(x + 12 + kw, y0 + 17 * i, v, "m")
        fits(v, w - 24 - kw, "m", f"{title}/{k}")
    return h


def done(h):
    return "\n".join(out), h


def ent(x, y, w, h, eid, title, sub="", dup=False):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="ee"/>')
    text(x + w / 2, y + (h / 2 - 3 if sub else h / 2 + 5), f"{eid} · {title}", "t2", "middle")
    if sub:
        text(x + w / 2, y + h / 2 + 14, sub, "m", "middle")
        fits(sub, w - 10, "m", title)
    if dup:
        out.append(f'<path d="M{x} {y + 14} L{x + 14} {y}" class="dupl"/>')


def badges(x, y, w, h, threats):
    for k, t in enumerate(threats):
        cx, cy = x + w - 20 - 34 * k, y + h - 14
        out.append(f'<rect x="{cx - 16}" y="{cy - 9}" width="32" height="18" rx="9" class="wb"/>')
        text(cx, cy + 4, t, "wbt", "middle")


# ================================================================ 1 · system context
out, P = [], "cx"
out.append('<rect x="470" y="28" width="700" height="430" rx="14" class="bnd"/>')
text(1158, 48, "system boundary: the app and the data it builds in memory", "lbs", "end")
box(605, 60, 210, 96, "data/mock_data.py", ["a made-up organization", "32 nodes, 48 edges", "typed by hand"], cls="dt")
box(510, 200, 400, 170, "GraphRAG vs vector RAG", [
    "one Python process: compare.py (CLI) or ui.py", "builds a NetworkX graph and a FAISS index",
    "answers each question both ways", "scores recall against 6 gold sets",
    "LangGraph · LangChain · Streamlit · pyvis"], cls="nd")
fl("M710 156 V198")
label(718, 182, "nodes, edges, document text")
person(160, 200, "User", "PM, lead or developer")
fl("M196 226 H508")
label(352, 218, "a question, or all six", "middle")
fl("M508 254 H196")
label(352, 270, "both answers, recall, graph view", "middle")
box(1240, 180, 300, 100, "OpenAI API", ["gpt-4o-mini: linking and answers",
                                       "text-embedding-3-small: 32 chunks,", "then each question"], cls="ex")
box(1240, 330, 300, 80, "PyPI", ["11 packages, “>=” versions only"], cls="ex")
fl("M912 220 H1238")
label(1062, 213, "node text, documents, questions, facts", "middle")
fl("M1238 250 H912")
label(1075, 243, "entities, answers, vectors", "middle")
fl("M1238 350 H912")
label(1075, 343, "packages, at install", "middle")
svg_ctx, H_CTX = done(480)

# ================================================================ 2 · high-level architecture
out, P = [], "ar"
out.append('<rect x="220" y="24" width="980" height="536" rx="14" class="bndc"/>')
text(240, 48, "ONE PYTHON PROCESS · compare.py (CLI) or ui.py (Streamlit) · everything in memory", "h")
out.append('<rect x="500" y="66" width="680" height="190" rx="10" class="cf"/>')
text(516, 88, "GraphRAG · a LangGraph workflow (graph_rag.py)", "t2")
for i, (t, s_) in enumerate((("link", "LLM extracts entity names + relation types; fuzzy-match to node IDs"),
                             ("fallback", "if no seeds: regex on node names + topic map"),
                             ("expand", "2 hops over in and out edges; relation filter, retried without if empty"),
                             ("docs", "attach the text of Document nodes in the subgraph"),
                             ("generate", "LLM answers from the facts (answer prompt)"))):
    yy = 102 + 30 * i
    out.append(f'<rect x="516" y="{yy}" width="96" height="24" rx="12" class="pl"/>')
    text(564, yy + 16, t, "pt", "middle")
    text(624, yy + 16, s_, "m")
    fits(s_, 540, "m", "GraphRAG steps")
box(240, 290, 220, 106, "compare.py · ui.py", ["+ questions.py: 6 questions,", "gold strings, score_recall;",
                                               "run both pipelines"], cls="nd")
box(500, 290, 200, 106, "build_graph()", ["NetworkX MultiDiGraph", "32 nodes, 48 edges"], tag="graph_builder.py",
    cls="ep")
box(740, 290, 200, 106, "data/mock_data.py", ["7 people · 4 projects", "6 skills · 6 tools · 5 docs",
                                              "4 decisions · 48 edges"], cls="dt")
box(980, 290, 200, 106, "_node_chunks()", ["one chunk per node", "own attributes only", "no edges"],
    tag="vector_rag.py", cls="ep")
out.append('<rect x="500" y="436" width="680" height="96" rx="10" class="cf"/>')
text(516, 458, "VectorRAG · FAISS in memory (vector_rag.py)", "t2")
text(516, 482, "embed the 32 chunks once (text-embedding-3-small)", "m")
text(516, 500, "per question: embed it, take the top 8 chunks, one LLM call (answer prompt)", "m")
fl("M738 343 H702")
fl("M600 288 V258")
label(608, 278, "graph")
fl("M942 343 H978")
fl("M1080 396 V434")
label(1088, 420, "32 chunks")
fl("M350 288 V160 H498", "both")
label(358, 210, "question,")
label(358, 224, "answer")
fl("M350 398 V484 H498", "both")
label(358, 440, "question,")
label(358, 454, "answer")
person(110, 300, "User", "browser or terminal")
fl("M146 328 H238")
label(182, 320, "question", "middle")
fl("M238 352 H146")
label(182, 368, "answers", "middle")
box(1290, 66, 250, 466, "OpenAI API", ["chat: gpt-4o-mini", "embeddings:", "text-embedding-3-small", "",
                                       "the only provider;", "no offline mode"], cls="ex")
fl("M1180 160 H1288", "both")
label(1245, 152, "2 calls", "middle")
fl("M1180 484 H1288", "both")
label(1245, 476, "embed, call", "middle")
svg_ar, H_AR = done(580)

# ================================================================ 3 · graph schema and the vector chunks
out, P = [], "sc"
header(20, 28, "THE GRAPH · node types (count) and relation types (count)")
NODES = {"Person": (40, 200, "7 · name, role, team"), "Project": (550, 200, "4 · name, status, dates, summary"),
         "Skill": (40, 420, "6 · name, category"), "Tool": (550, 420, "6 · name, vendor"),
         "Document": (300, 60, "5 · title, type, content"), "Decision": (300, 330, "4 · title, date, rationale")}
for name_, (x, y, sub) in NODES.items():
    out.append(f'<rect x="{x}" y="{y}" width="220" height="64" rx="9" class="nd"/>')
    text(x + 12, y + 24, name_, "t")
    text(x + 12, y + 44, sub, "m")
    fits(sub, 196, "m", name_)
fl("M260 222 H548")
label(404, 214, "WORKED_ON (11) · role", "middle")
fl("M150 200 V92 H298")
label(158, 140, "AUTHORED (5)")
fl("M520 92 H660 V198")
label(590, 84, "ABOUT (5)", "middle")
fl("M150 264 V418")
label(158, 350, "HAS_SKILL (9) · level")
fl("M660 264 V418")
label(668, 350, "USED_TOOL (8)")
fl("M260 252 H280 V362 H298")
label(286, 304, "APPROVED (6)")
fl("M520 362 H610 V266")
label(602, 312, "DECISION_FOR (4)", "end")
text(20, 520, "No dates on edges; one audit, so “last” is never tested.", "lbs")
header(800, 28, "WHAT EACH PIPELINE CAN SEE")
out.append('<rect x="800" y="44" width="740" height="214" rx="9" class="nt"/>')
text(816, 66, "Vector RAG: one chunk per node, attributes only (vector_rag.py)", "t3")
for i, line in enumerate((
        "Person: Alice Chen. Role: Compliance Lead. Team: Risk & Compliance.",
        "Project: Q3 2025 SOC2 Compliance Audit. Status: Completed. ...",
        "Decision: Adopt 3-tier usage-based pricing model (date: 2025-05-20).",
        "  Rationale: Reduce SMB churn and increase NRR ..."), 0):
    text(816, 92 + 18 * i, line, "pm")
text(816, 176, "32 chunks, 3,919 characters in all. None of the 48 edges is written in any chunk:", "s")
text(816, 194, "nothing says Alice worked on the audit or Eve approved the pricing decision.", "s")
text(816, 222, "Only some document and decision text links things, e.g. the audit report names Drata", "s")
text(816, 240, "and AWS Audit Manager.", "s")
out.append('<rect x="800" y="276" width="740" height="214" rx="9" class="repb"/>')
text(816, 298, "GraphRAG: the subgraph as fact lines (serialize_subgraph), plus document text", "t3")
for i, line in enumerate((
        "- [Person] Alice Chen — role=Compliance Lead; team=Risk & Compliance",
        "- Alice Chen —WORKED_ON→ Q3 2025 SOC2 Compliance Audit {'role': 'Lead'}",
        "- Eve Johnson —APPROVED→ Adopt 3-tier usage-based pricing model",
        "- Q3 2025 SOC2 Compliance Audit —USED_TOOL→ Okta")):
    text(816, 324 + 18 * i, line, "pm")
text(816, 412, "Every edge in the expanded subgraph becomes a line the model can quote.", "s")
text(816, 430, "The comparison is therefore between an index with the edges and one without.", "s")
text(816, 456, "Our proxy check: added as 48 sentences, most edges become retrievable; at top 16,", "s")
text(816, 474, "every needed one for Q1, Q2, Q4 and Q5 (figure 10).", "s")
svg_sc, H_SC = done(540)

# ================================================================ 4 · data flow (level 1, Gane-Sarson)
out, P = [], "df"
store(520, 30, 380, 50, "D1", "data/mock_data.py", ["nodes, edges, document text"])
proc(200, 120, 180, 92, "P1", "Build graph", ["build_graph()", "NetworkX, in memory"])
proc(1000, 120, 180, 92, "P2", "Build vector index", ["32 node chunks", "embed into FAISS"])
store(160, 250, 280, 50, "D2", "graph (memory)", ["32 nodes, 48 edges"])
store(960, 250, 280, 50, "D3", "FAISS index (memory)", ["32 vectors + chunk text"])
fl("M520 65 H290 V118")
label(298, 100, "nodes, edges", cls="lbs")
fl("M900 55 H1090 V118")
label(1000, 47, "node attributes", "middle", "lbs")
fl("M290 212 V248")
label(298, 236, "graph", cls="lbs")
fl("M1090 212 V248")
label(1098, 236, "vectors + text", cls="lbs")
ent(1300, 120, 220, 290, "E2", "OpenAI API", "chat + embeddings", dup=True)
fl("M1180 166 H1298", "both")
label(1239, 158, "chunks ↔ vectors", "middle", "lbs")
ent(600, 150, 180, 60, "E1", "User", "browser or terminal")
proc(590, 340, 200, 92, "P5", "Run and score", ["compare.py or ui.py", "score_recall per answer"])
fl("M650 210 V338")
label(642, 290, "question", "end", "lbs")
fl("M730 338 V212")
label(738, 290, "answers, recall, graph view", cls="lbs")
fl("M440 275 H560 V356 H588")
label(500, 267, "all nodes + attributes", "middle", "lbs")
proc(200, 340, 190, 92, "P3", "Retrieve from graph", ["link, fallback, expand,", "attach documents"])
proc(200, 480, 190, 92, "P4", "Answer from facts", ["answer prompt", "gpt-4o-mini"])
proc(1000, 340, 190, 92, "P6", "Retrieve and answer", ["embed question, top 8,", "answer prompt"])
fl("M290 300 V338")
label(298, 326, "nodes, edges", cls="lbs")
fl("M520 45 H120 V370 H198")
label(112, 210, "document text", "end", "lbs")
fl("M588 384 H392")
label(490, 400, "question", "middle", "lbs")
fl("M290 432 V478")
label(298, 462, "question, facts + document text", cls="lbs")
fl("M392 526 H640 V434")
label(520, 518, "graph answer + subgraph", "middle", "lbs")
fl("M1090 300 V338")
label(1098, 326, "top 8 chunks", cls="lbs")
fl("M792 370 H998")
label(895, 362, "question", "middle", "lbs")
fl("M998 400 H792")
label(895, 416, "vector answer + chunks", "middle", "lbs")
fl("M1190 386 H1298", "both")
label(1244, 378, "question, prompt", "middle", "lbs")
label(1244, 404, "vector, answer", "middle", "lbs")
store(700, 480, 280, 50, "D4", "questions.py", ["6 questions + gold strings"])
fl("M760 478 V434")
label(768, 462, "questions + gold", cls="lbs")
ent(160, 640, 280, 56, "E2", "OpenAI API", "chat", dup=True)
fl("M200 386 H140 V668 H158", "both")
label(132, 540, "question ↔ entities,", "end", "lbs")
label(132, 554, "relations", "end", "lbs")
fl("M300 572 V638", "both")
label(308, 610, "prompt ↔ answer", cls="lbs")
svg_dfd, H_DFD = done(716)

# ================================================================ 5 · detailed design
out, P = [], "ds"
FILES = [
    ("data/mock_data.py", ["PEOPLE 7 · PROJECTS 4 · SKILLS 6 · TOOLS 6 · DOCUMENTS 5 · DECISIONS 4",
                           "RELATIONSHIPS: 48 (src, dst, type, attrs); all_nodes() adds 'kind'"], []),
    ("graph_builder.py", ["build_graph(): MultiDiGraph, edge key = relation type",
                          "_fuzzy_match(name, cutoff 0.6): first substring match, then difflib",
                          "llm_link_entities: structured output {entities, relations}",
                          "heuristic_link_entities: whole-name regex + _TOPIC_MAP (10 keys)",
                          "expand_subgraph(seeds, hops, relation_filter): BFS out and in edges",
                          "serialize_subgraph: '### Entities' and '### Relationships' lines"], [6, 4, 3]),
    ("graph_rag.py", ["LangGraph: link → (no seeds) fallback → expand → docs → generate",
                      "expand: retry with no filter if the filtered subgraph has 0 edges",
                      "_PROMPT: graph facts first, documents for detail; say so if insufficient",
                      "GraphRAG(hops=2).answer(): answer, seed_ids, linker_used, subgraph, graph_facts …"], [5]),
    ("vector_rag.py", ["_node_chunks(): one 'Person: … Role: … Team: …' chunk per node",
                       "FAISS.from_documents(32 chunks, text-embedding-3-small); k = 8",
                       "_PROMPT: answer only from the retrieved chunks; say so if insufficient"], [2, 1]),
    ("questions.py", ["6 questions; must_include strings; score_recall: substring, case-insensitive"], [7]),
    ("compare.py · ui.py", ["compare: VectorRAG(k=8), GraphRAG(hops=2), print a tabulate table",
                            "ui: Streamlit, pyvis graph with highlights, recall per answer, no login",
                            "ui: checks OPENAI_API_KEY before anything loads .env"], [11, 8]),
    ("llm.py · requirements.txt · lib/", ["get_llm: gpt-4o-mini (default; OPENAI_MODEL), temperature 0",
                                          "get_embeddings: text-embedding-3-small (default; OPENAI_EMBED_MODEL)",
                                          "requirements: '>=' only; lib/: vis-network 9.1.2, tom-select"],
     [10, 9]),
]
y = 20
for title, lines, notes in FILES:
    h = 34 + 16 * len(lines) + 8
    box(20, y, 760, h, title, lines, cls="nd" if title.endswith(".py") and "data" not in title else "ep",
        warn=notes)
    y += h + 12
H_D5 = y
NOTES5 = [
    ("Vector chunks hold each node's own attributes; none of the 48 edges is indexed, so the vector",
     "side cannot see who worked on, approved or authored anything."),
    ("README: “Same data — both index every entity in the graph.” Entities yes; edges no.", ""),
    ("_fuzzy_match returns the first node, in node order, whose name contains or is inside the name:",
     "5 of the 32 node names resolve to the wrong node (our check), e.g. “AWS Audit Manager” → “AWS”."),
    ("The topic map's 10 keys alias the four projects; alone the fallback links every question to the",
     "right project or person (our check), so the benchmark can't show what the LLM linker adds."),
    ("hops=2 everywhere. The three skills in Q3's gold are 3 hops from Bob; unfiltered, 2 hops",
     "already return 44–66% of the nodes (our check)."),
    ("Expansion walks every connected node; nothing checks what the asker may see.", ""),
    ("Substring recall: no precision, no grounding. Q3's gold asks for three skills 2 hops can't reach,",
     "omits AWS and Python, which they can, and its “SOC2 Compliance” is inside a project name."),
    ("compare.py prints the recall table and saves nothing; no results are published.", ""),
    ("requirements.txt pins nothing (“>=” only); OpenAI is the only provider, with no offline mode.", ""),
    ("lib/ holds generated pyvis assets (vis-network 9.1.2, tom-select) committed to the repo.", ""),
    ("ui.py checks OPENAI_API_KEY before anything loads .env, so with the key only in .env the UI stops;",
     "compare.py loads .env through llm.py and runs."),
]
out.append(f'<rect x="810" y="20" width="730" height="{H_D5 - 32}" rx="9" class="nt"/>')
text(826, 44, "Review notes · numbered on the files they affect", "t2")
step = (H_D5 - 90) / len(NOTES5)
for i, (a, b) in enumerate(NOTES5):
    yy = 76 + i * step
    dot(838, yy - 4, i + 1)
    text(858, yy, a, "m")
    fits(a, 670, "m", f"note {i + 1}")
    if b:
        text(858, yy + 16, b, "m")
        fits(b, 670, "m", f"note {i + 1}")
svg_design, H_DESIGN = done(H_D5 + 8)

# ================================================================ 6 · sequence: one question through GraphRAG
out, P = [], "sq"
LIFE = [("compare.py", "or ui.py", 110), ("GraphRAG app", "LangGraph", 400), ("OpenAI", "gpt-4o-mini", 760),
        ("graph_builder", "NetworkX, in memory", 1100), ("score_recall", "questions.py", 1400)]
SEQ_END = 700
for name_, sub, x in LIFE:
    out.append(f'<rect x="{x - 90}" y="24" width="180" height="50" rx="8" class="ep"/>')
    text(x, 46, name_, "t2", "middle")
    text(x, 63, sub, "m", "middle")
    out.append(f'<path d="M{x} 74 V{SEQ_END}" class="life"/>')
X = {n: x for n, _, x in LIFE}
for who, y1, y2 in (("compare.py", 106, 672), ("GraphRAG app", 116, 596), ("OpenAI", 150, 192),
                    ("OpenAI", 514, 556), ("graph_builder", 324, 366), ("graph_builder", 404, 442),
                    ("score_recall", 624, 668)):
    out.append(f'<rect x="{X[who] - 6}" y="{y1}" width="12" height="{y2 - y1}" class="act"/>')


def msg(a, b, y, s, ret=False, n=None):
    x1, x2 = X[a] + (6 if X[b] > X[a] else -6), X[b] + (-6 if X[b] > X[a] else 6)
    fl(f"M{x1} {y} H{x2}", "ret" if ret else "ln")
    text((x1 + x2) / 2, y - 7, s, "msg" if not ret else "lbl", "middle")
    fits(s, abs(x2 - x1) + 60, "msg", "sequence")
    if n:
        out.append(f'<rect x="{X["OpenAI"] + 20}" y="{y - 13}" width="{14 + 6.6 * len(n)}" height="19" rx="9.5" '
                   f'class="llm"/>')
        text(X["OpenAI"] + 27 + 3.3 * len(n), y + 1, n, "llmt", "middle")


def frame(y1, y2, x1, x2, tab, guard, tabw=44):
    out.append(f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" rx="6" class="frame"/>')
    out.append(f'<path d="M{x1} {y1} H{x1 + tabw} V{y1 + 14} L{x1 + tabw - 10} {y1 + 22} H{x1} Z" class="frtab"/>')
    text(x1 + 8, y1 + 15, tab, "frt")
    text(x1 + tabw + 10, y1 + 15, guard, "frt")


def self_msg(who, y, s):
    x = X[who] + 6
    out.append(f'<path d="M{x} {y} H{x + 40} V{y + 16} H{x + 2}" class="ln" marker-end="url(#{P}ar)"/>')
    text(x + 48, y + 12, s, "msg")


msg("compare.py", "GraphRAG app", 116, "answer(question)")
msg("GraphRAG app", "OpenAI", 156, "link: extract entities + relation types (structured)", n="1")
msg("OpenAI", "GraphRAG app", 184, "{entities: [...], relations: [...]}", ret=True)
self_msg("GraphRAG app", 200, "fuzzy-match names → seed node IDs")
frame(236, 300, 360, 1180, "opt", "[no seeds, or the LLM call failed]")
self_msg("GraphRAG app", 266, "regex on node names + topic map → seeds")
msg("GraphRAG app", "graph_builder", 330, "expand_subgraph(seeds, hops=2, relation filter)")
msg("graph_builder", "GraphRAG app", 358, "subgraph", ret=True)
frame(376, 452, 360, 1180, "opt", "[0 edges and a filter was set]")
msg("GraphRAG app", "graph_builder", 410, "expand again with no filter")
msg("graph_builder", "GraphRAG app", 436, "subgraph", ret=True)
self_msg("GraphRAG app", 466, "serialize facts; attach text of Document nodes")
msg("GraphRAG app", "OpenAI", 520, "answer prompt: facts + document text + question", n="2")
msg("OpenAI", "GraphRAG app", 548, "the answer", ret=True)
msg("GraphRAG app", "compare.py", 590, "{answer, seed_ids, subgraph, graph_facts, …}", ret=True)
msg("compare.py", "score_recall", 630, "score_recall(answer, gold strings)")
msg("score_recall", "compare.py", 660, "recall, hits, misses", ret=True)
text(1500, SEQ_END + 22, "Vector RAG for the same question: embed it, FAISS top 8, one answer call.", "lbs", "end")
text(1500, SEQ_END + 40, "solid arrow: a call · dashed, open arrow: its reply · bars: active · numbers: LLM calls",
     "m", "end")
svg_seq, H_SEQ = done(SEQ_END + 54)

# ================================================================ 7 · the two contexts for Q1
out, P = [], "cq"
header(20, 28, "Q1 · “Who worked on the last compliance audit and what tools did they use?”")
text(20, 50, "Gold: Alice Chen, Bob Martinez, Frank Lee, AWS Audit Manager, Drata, Okta", "s")
out.append('<rect x="20" y="66" width="740" height="330" rx="9" class="nt"/>')
text(36, 88, "VECTOR RAG · top 8 chunks (our proxy ranking with a local model)", "t3")
VEC = ["Tool: AWS Audit Manager (vendor: AWS).", "Person: Alice Chen. Role: Compliance Lead. Team: Risk & ...",
       "Project: Q3 2025 SOC2 Compliance Audit. Status: Completed. ...", "Skill: SOC2 Compliance (category: ...",
       "Document: Q3 2025 SOC2 Audit Final Report ... Drata ... AWS Audit ...",
       "Decision: Use AWS Audit Manager as primary cloud control ...", "Tool: Okta (vendor: Okta).",
       "Person: Frank Lee. Role: Security Engineer. Team: Security."]
for i, line in enumerate(VEC):
    text(36, 114 + 20 * i, f"{i + 1}. {line}", "pm")
    fits(line, 690, "pm", "vector top 8")
text(36, 290, "5 of the 6 gold names are here; Bob Martinez is not.", "s")
text(36, 310, "No chunk says who worked on the audit. Only the report's text (and,", "s")
text(36, 328, "for AWS Audit Manager, a decision's rationale) ties tools to it.", "s")
text(36, 354, "An answer naming Alice and Frank would be a guess from job titles,", "s")
text(36, 372, "and substring recall would count it.", "s")
out.append('<rect x="800" y="66" width="740" height="330" rx="9" class="repb"/>')
text(816, 88, "GRAPHRAG · 2-hop subgraph, WORKED_ON and USED_TOOL only (assumed filter)", "t3")
GR = ["Alice Chen —WORKED_ON→ Q3 2025 SOC2 Compliance Audit {role: Lead}",
      "Frank Lee —WORKED_ON→ Q3 2025 SOC2 ... {role: Security Reviewer}",
      "Bob Martinez —WORKED_ON→ Q3 2025 SOC2 ... {role: Evidence Engineer}",
      "Q3 2025 SOC2 Compliance Audit —USED_TOOL→ AWS Audit Manager",
      "Q3 2025 SOC2 Compliance Audit —USED_TOOL→ Drata",
      "Q3 2025 SOC2 Compliance Audit —USED_TOOL→ Okta",
      "Frank Lee, Bob Martinez —WORKED_ON→ Zero-Trust Security Rollout",
      "Bob Martinez —WORKED_ON→ ML Recommendation Engine"]
for i, line in enumerate(GR):
    text(816, 114 + 20 * i, line, "pm")
    fits(line, 700, "pm", "graph facts")
text(816, 290, "Every gold item, each with the edge that makes it an answer.", "s")
text(816, 310, "9 nodes, 10 edges, 1,451 characters with this filter;", "s")
text(816, 328, "with no filter, 17 nodes and 3,535 characters (our check).", "s")
text(816, 354, "Both prompts ask the model to name every person and tool,", "s")
text(816, 372, "and to say so when the context is insufficient.", "s")
text(20, 418, "Abridged: entity lines omitted, long names shortened; on the GraphRAG side two WORKED_ON lines are "
              "merged and “Zero-Trust —USED_TOOL→ Okta” is left out. The vector side is our proxy ranking, "
              "not 2C's run.", "lbs")
svg_cq, H_CQ = done(436)

# ================================================================ 8 · why Q3 needs three hops
out, P = [], "hp"
header(20, 28, "Q3 (benchmark question 3) · “Which projects is Bob Martinez involved in, and what skills do his "
               "teammates bring?”")
for x, t in ((145, "start"), (455, "hop 1"), (820, "hop 2"), (1240, "hop 3")):
    text(x, 70, t, "rl", "middle")
out.append('<rect x="24" y="82" width="946" height="480" rx="14" class="bndc"/>')
text(958, 104, "within 2 hops of Bob: what GraphRAG(hops=2) can reach", "lbs", "end")


def nbox(x, y, t, sub, cls="nd", w=210):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="46" rx="8" class="{cls}"/>')
    text(x + 10, y + 19, t, "t3")
    text(x + 10, y + 36, sub, "m")
    fits(t, w - 20, "t", t)
    fits(sub, w - 20, "m", t)


nbox(40, 280, "Bob Martinez", "Person · the seed")
PROJ = [("Q3 2025 SOC2 Compliance Audit", 140), ("Zero-Trust Security Rollout", 220), ("ML Recommendation Engine", 300)]
for t, yy in PROJ:
    nbox(330, yy, t, "Project · WORKED_ON", "nd", 250)
    fl(f"M250 303 H290 V{yy + 23} H328")
nbox(330, 400, "Python, AWS", "Bob's own skills · HAS_SKILL", "ep", 250)
fl("M250 303 H290 V423 H328")
text(330, 476, "Alice's AWS and David's Python are in reach:", "s")
text(330, 494, "they are the same skill nodes Bob has", "s")
text(330, 512, "(Bob → AWS ← Alice), two hops out.", "s")
MATES = [("Alice Chen", 140, "teammate · has AWS, like Bob"), ("Frank Lee", 210, "teammate"),
         ("Grace Patel", 280, "teammate"), ("David Kim", 350, "teammate · has Python, like Bob")]
for t, yy, sub in MATES:
    nbox(700, yy, t, sub, "nd", 240)
for path in ("M580 163 H698",                      # audit -> Alice
             "M580 163 H620 V226 H698",            # audit -> Frank
             "M580 243 H698",                      # zero-trust -> Frank
             "M580 243 H650 V303 H698",            # zero-trust -> Grace
             "M580 323 H620 V373 H698"):           # ML engine -> David
    fl(path)
nbox(700, 440, "tools, documents, decisions", "also within 2 hops", "ep", 240)
SK = [("SOC2 Compliance", 140, "Alice's other skill · HAS_SKILL"),
      ("Penetration Testing, SOC2 Compliance", 210, "Frank's skills · HAS_SKILL"),
            ("Machine Learning", 350, "David's other skill · HAS_SKILL")]
for t, yy, sub in SK:
    nbox(1090, yy, t, sub, "ex", 300)
    fl(f"M940 {yy + 23} H1088", "lnd")
text(1090, 307, "Grace has no skills recorded.", "s")
for i, line in enumerate(("Gold names three skills, all here, three hops", "out: SOC2 Compliance, Machine Learning and",
                          "Penetration Testing. It omits AWS and Python,", "the two that are in reach.")):
    text(1090, 420 + 18 * i, line, "s")
for i, line in enumerate(("“SOC2 Compliance” also matches the project", "name, so naming the project scores the skill.")):
    text(1090, 500 + 18 * i, line, "s")
for i, line in enumerate(("Arrows show the walk from Bob; expansion follows", "edges both ways (WORKED_ON points from person",
                          "to project). Dashed: the third hop.")):
    text(1090, 548 + 18 * i, line, "m")
svg_hp, H_HP = done(610)

# ================================================================ 9 · threat model
out, P = [], "tm"
TM_BOTTOM = 780
out.append(f'<rect x="226" y="40" width="486" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(242, 62, "TB2 · the machine running the app", "tbt")
out.append(f'<rect x="790" y="40" width="224" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(806, 62, "TB3 · third-party services", "tbt")
out.append(f'<path d="M206 40 V{TM_BOTTOM + 30}" class="tbl"/>')
text(200, 56, "TB1", "tbt", "end")
text(200, 72, "browser", "lbs", "end")
person(70, 110, "User", "browser or terminal")


def tbox(x, y, w, h, title, lines, threats, cls="bx"):
    box(x, y, w, h, title, lines, cls=cls)
    badges(x, y, w, h, threats)


tbox(246, 90, 446, 110, "Streamlit app (ui.py)", ["no login; shows every node, most attributes",
                                                  "as tooltips; both answers"], ["T11", "T10", "T7", "T6", "T1"], cls="ep")
tbox(246, 220, 446, 130, "graph_builder and both pipelines", ["expansion walks any connected node;",
                                                           "node text, facts and documents go into prompts"],
     ["T4", "T2", "T1"], cls="nd")
store(246, 370, 200, 96, "D1", "mock_data.py", ["people, roles, skills,", "decisions; edges by hand"])
badges(246, 370, 200, 96, ["T5", "T3"])
store(486, 370, 206, 96, "D5", ".env / environment", ["OPENAI_API_KEY"])
badges(486, 370, 206, 96, ["T9"])
tbox(246, 486, 446, 80, "Installed packages and lib/", ["“>=” versions; vendored vis-network 9.1.2"], ["T8"])
fl("M469 218 V202", "both")
label(477, 214, "questions, answers, whole graph", cls="lbs")
fl("M346 368 V352")
label(354, 364, "graph data", cls="lbs")
fl("M589 368 V352")
label(597, 364, "API key", cls="lbs")
tbox(806, 90, 192, 260, "OpenAI API", ["node text, documents,", "questions, graph facts;", "GraphRAG: 2 chat calls;",
                                       "vector: 1 embed + 1 chat;", "32 chunk embeds at start"], ["T10", "T2"],
     cls="ex")
tbox(806, 486, 192, 80, "PyPI", ["packages at install"], ["T8"], cls="ex")
fl("M110 130 H244")
text(200, 122, "questions", "lbs", "end")
fl("M244 170 H110")
text(200, 186, "answers, graph", "lbs", "end")
fl("M694 260 H804", "lnr")
text(751, 253, "prompts", "lbs", "middle")
fl("M804 310 H694", "lnr")
text(751, 303, "answers", "lbs", "middle")
fl("M804 526 H694", "lnr")
text(751, 519, "packages", "lbs", "middle")
out.append('<rect x="260" y="590" width="420" height="34" rx="8" class="nt"/>')
text(272, 606, "Red arrows: data crossing TB3, to or from a third party", "m")
text(272, 619, "TB1 browser → app · TB2 the app's machine · TB3 outside services", "m")
THREATS = [
    ("T1", "Information disclosure · no access control", "Expansion pulls in any connected node, and the UI shows",
     "every node: restricted decisions or HR data reach anyone.", "today: none"),
    ("T2", "Information disclosure · third party", "Names, roles, decisions, document text and questions go to",
     "OpenAI for embeddings and answers.", "today: mock data only"),
    ("T3", "Information disclosure · personnel data", "Who worked with whom, and who has which skill, is",
     "employee data; queries can profile people.", "today: none"),
    ("T4", "Tampering · prompt injection", "Document and node text go into prompts; a planted document",
     "could steer the answer or invent an approval.", "today: two prompt rules only"),
    ("T5", "Tampering · graph integrity", "Edges carry no source or date; a wrong or edited edge (who",
     "approved) is presented as fact.", "today: none"),
    ("T6", "Spoofing · no login", "Anyone who can reach the Streamlit port can ask anything.", "",
     "today: none"),
    ("T7", "Repudiation · no audit trail", "Nothing records who asked what, or which nodes an answer",
     "exposed.", "today: none"),
    ("T8", "Tampering · supply chain", "requirements.txt pins nothing (“>=” only); lib/ holds committed",
     "copies of front-end libraries.", "today: none"),
    ("T9", "Information disclosure · secrets", "OPENAI_API_KEY from the shell or .env (ui.py checks it before",
     "loading .env); any installed package can read it.", "today: kept out of the code"),
    ("T10", "Denial of service · cost", "No budget or rate limit; each GraphRAG question makes two",
     "chat calls, each vector question one, plus embeddings.", "today: none"),
    ("T11", "Elevation of privilege · no roles", "There are no roles to escalate: every user already has",
     "full access to every node (see T1, T6).", "today: none"),
]
out.append(f'<rect x="1040" y="40" width="500" height="{TM_BOTTOM - 40}" rx="12" class="nt"/>')
text(1056, 64, "Threats (STRIDE) and what the code does today", "t2")
for i, (tid, title, a, b, today) in enumerate(THREATS):
    yy = 92 + 62 * i
    out.append(f'<rect x="1054" y="{yy - 13}" width="34" height="18" rx="9" class="wb"/>')
    text(1071, yy, tid, "wbt", "middle")
    text(1096, yy, title, "t3")
    text(1096, yy + 15, a, "m")
    if b:
        text(1096, yy + 29, b, "m")
    text(1096, yy + 43 if b else yy + 29, today, "mi")
    for s_ in (a, b):
        fits(s_, 430, "m", tid)
svg_tm, H_TM = done(TM_BOTTOM + 44)

# ================================================================ 10 · the comparison
out, P = [], "ev"
box(14, 40, 300, 150, "questions.py · 6 questions", ["Q1–Q5: relational, multi-hop", "Q6: summarize a document",
                                                      "gold: strings the answer", "should contain"], cls="dt")
box(360, 40, 300, 66, "Vector RAG", ["node chunks, top 8, one LLM call"], cls="ep")
box(360, 124, 300, 66, "GraphRAG", ["link, 2 hops, facts + docs, two LLM calls"], cls="ep")
for yy in (73, 157):
    fl(f"M314 115 H337 V{yy} H358")
box(706, 60, 250, 110, "score_recall", ["substring, case-insensitive", "hits ÷ gold strings",
                                        "no precision, no grounding"], cls="nd")
for yy in (73, 157):
    fl(f"M660 {yy} H683 V115 H704")
fl("M164 190 V222 H831 V172")
label(500, 216, "gold strings", "middle")
box(1000, 60, 230, 110, "compare.py", ["prints a recall table", "per question", "saves nothing"], tag="no results "
    "published", cls="nd")
fl("M956 115 H998")
ROWS = [("", "needed", "A", "B", "C", "G"), ("Q1", "6", "–", "4", "6", "6"), ("Q2", "3", "–", "3", "3", "3"),
        ("Q3", "14", "–", "3", "3", "10"), ("Q4", "2", "–", "1", "2", "2"), ("Q5", "4", "–", "4", "4", "4")]
out.append('<rect x="1250" y="30" width="290" height="258" rx="9" class="repb"/>')
text(1262, 52, "Edge facts retrieved (our checks)", "t3")
for r, row in enumerate(ROWS):
    yy = 78 + 24 * r
    for c, val in enumerate(row):
        xx = (1262, 1336, 1388, 1430, 1472, 1514)[c]
        text(xx, yy, val, "t3" if r == 0 or c == 0 else "s", "start" if c == 0 else "middle")
for i, line in enumerate(("A: 2C's chunks, top 8 (no edges: –)", "B: + edge sentences, top 8 · C: top 16",
                          "B, C: proxy embedding model", "G: 2-hop GraphRAG, fallback seeds, no filter")):
    text(1262, 222 + 16 * i, line, "m")
    fits(line, 266, "m", "table key")
box(14, 306, 500, 166, "What the benchmark cannot show", [
    "whether vector search fails, or only lacks the edges",
    "whether the LLM linker helps (the fallback alone links all 6)",
    "behaviour at a size where retrieval has to choose",
    "precision, grounding, paraphrases, spread over runs",
    "time, permissions, unanswerable questions"], cls="nt")
box(534, 306, 500, 166, "What a fair version adds", [
    "the same facts on both sides: edges as sentences or",
    "neighbour lists, and a full-context control while it fits",
    "user-written questions, held out from the topic map",
    "answers that cite node IDs; precision and recall;",
    "every named entity checked against the facts"], cls="nt")
box(1054, 306, 486, 166, "Our offline checks (retrieval only)", [
    "none of the 48 edges is in the vector chunks;",
    "with edge sentences, top 16 finds every needed edge",
    "for Q1, Q2, Q4 and Q5, but 3 of 14 for Q3; GraphRAG's",
    "2 hops hold 10 of Q3's 14, not the 3 gold skills;",
    "5 of 32 names mis-linked; no answers generated"], cls="repb")
svg_ev, H_EV = done(492)

# ================================================================ 11 · the recommended architecture
out, P = [], "rc"
header(20, 28, "WHAT AN FDE WOULD BUILD · the number in a corner is the 2.5 decision that part answers")
text(20, 58, "BUILD AND MAINTAIN THE GRAPH", "rl")
for i, (t, l) in enumerate((("HR system (HRIS)", "people, roles, skills"), ("Project tools", "who worked on what, when"),
                            ("Decision register", "decisions, approvers"),
                            ("Wiki and documents", "documents, authors, notes"))):
    box(20, 70 + 66 * i, 200, 58, t, [l], cls="ex")
box(270, 70, 220, 190, "Connectors", ["recorded edges, synced on a", "schedule or change feed;",
                                      "source and date kept;", "document metadata and", "permissions too"],
    cls="nd", tag="1")
for y in (99, 165, 231):
    fl(f"M222 {y} H268")
fl("M222 282 H245 V250 H268")
box(270, 280, 220, 90, "LLM extraction", ["edges stated in text,", "checked by a person"], cls="nd", tag="1")
fl("M222 312 H268")
box(540, 140, 200, 120, "Entity resolution", ["one node per person or", "project across systems,", "via shared IDs"],
    cls="nd", tag="1")
fl("M492 165 H538")
fl("M492 325 H515 V235 H538")
box(790, 120, 280, 160, "Graph database", ["every edge with its source,", "dates (valid from / to)",
                                           "and permissions; query-time", "access control; document",
                                           "text kept on document nodes"], cls="dt", tag="2, 3")
fl("M742 200 H788")
box(790, 40, 280, 58, "Identity groups", ["Entra ID or Okta groups"], cls="ex")
fl("M930 98 V118")
label(938, 112, "who may see what")
box(1120, 40, 420, 240, "Governance", ["purposes agreed with Legal and Privacy (DPIA),",
                                       "and the works council where one exists",
                                       "edge definitions: what “worked on”, “approved”",
                                       "and “expert in” mean, and which record proves it",
                                       "a named owner for graph quality", "leavers, moves and reorgs synced"],
    cls="nt", tag="1, 2")
text(20, 420, "ANSWER A QUESTION", "rl")
person(60, 450, "Asker", "signed in (SSO)")
box(120, 440, 180, 110, "Question router", ["by question type:", "lookup, path, list,", "or prose"], cls="nd",
    tag="6")
fl("M86 495 H118")
box(330, 440, 200, 110, "Entity linking", ["names → node IDs;", "longest name first, or", "embeddings + threshold;",
                                           "tested on its own"], cls="nd", tag="4, 5")
fl("M302 495 H328")
box(560, 430, 240, 58, "Query templates", ["known question shapes"], cls="nd", tag="6")
box(560, 498, 240, 74, "Text-to-Cypher", ["schema in the prompt,", "validated, read-only role"], cls="nd", tag="6")
box(560, 582, 240, 74, "Hybrid", ["graph facts + passages", "for prose questions"], cls="nd", tag="6, 7")
for y in (459, 535, 619):
    fl(f"M532 495 H545 V{y} H558")
box(850, 470, 230, 130, "Permission-aware traversal", ["the asker's rights only;", "derived edges: the stricter",
                                                       "permission; restricted", "nodes hidden; k-hop",
                                                       "expansion as fallback"], cls="nd", tag="6, 14")
fl("M802 459 H825 V505 H848")
fl("M802 535 H848")
fl("M802 619 H825 V565 H848")
fl("M960 282 V468")
label(968, 380, "facts, with permissions")
box(1120, 470, 180, 130, "Rank and trim", ["keep the facts", "the question needs"], cls="nd", tag="7")
box(1340, 470, 200, 130, "Answer (LLM)", ["cites node and edge IDs;", "approved provider", "or gateway"], cls="nd",
    tag="10, 11")
fl("M1082 535 H1118")
fl("M1302 535 H1338")
fl("M1440 602 V680 H60 V562")
label(750, 674, "answer, citing its sources", "middle")
box(20, 700, 1520, 74, "Evaluation, before and during the pilot", [
    "30–50 user questions, a third held out; five set-ups: vector, vector + edge sentences, GraphRAG, graph queries, "
    "and the full graph as a control while it fits",
    "gold sets as node IDs, precision and recall, every named entity checked against the facts; linking accuracy "
    "measured on its own; repeated runs stored"], cls="nt", tag="8, 9, 11, 12")
svg_rc, H_RC = done(790)

# ================================================================ page
FIGS = [
    ("context", "System context", "Before anything else: what the system is, who uses it, and what it depends on.",
     svg_ctx, 1560, H_CTX,
     "System context: a user asks questions of one Python app that builds a graph and a vector index from a "
     "hand-written mock organization, calls the OpenAI API for linking, embeddings and answers, and installs "
     "packages from PyPI."),
    ("architecture", "High-level architecture", "Then the parts and where they run: one process, two pipelines.",
     svg_ar, 1560, H_AR,
     "High-level architecture: inside one Python process, the mock data feeds a NetworkX graph used by a LangGraph "
     "GraphRAG workflow and node chunks used by a FAISS vector pipeline; compare.py and ui.py run both and score "
     "recall; OpenAI provides chat and embeddings."),
    ("schema", "Graph schema and the vector chunks", "Then what the data is, and what each side can see of it.",
     svg_sc, 1560, H_SC,
     "Graph schema: six node types and seven relation types with counts; the vector chunks hold node attributes "
     "only, while GraphRAG serializes edges as fact lines."),
    ("dataflow", "Data flow (level 1)", "Then what data moves between the parts, and where it is stored.",
     svg_dfd, 1560, H_DFD,
     "Level-1 data flow: the mock data builds the graph and the vector index; the run-and-score process sends each "
     "question to graph retrieval and to vector retrieval, collects both answers, and scores them against the gold "
     "strings, and shows the graph view from the stored graph; OpenAI is called for linking, embeddings and answers."),
    ("design", "Detailed design", "Then each file's key functions and settings, with what is broken.",
     svg_design, 1560, H_DESIGN,
     "Detailed design: the repository's files with their key functions and settings, and eleven numbered review notes, "
     "from the vector chunks without edges to the UI's .env check."),
    ("sequence", "Sequence: one question", "Then one question through GraphRAG, call by call, in time order.",
     svg_seq, 1560, H_SEQ,
     "Sequence of one question through GraphRAG: an OpenAI call extracts entities and relations, names are "
     "fuzzy-matched to seeds with a fallback if none match, the graph is expanded two hops, retried without the "
     "filter if empty, facts and documents go to a second OpenAI call, and the answer is scored."),
    ("contexts", "The two contexts for Q1", "Then what each side actually hands the model for the same question.",
     svg_cq, 1560, H_CQ,
     "The two contexts for Q1: the vector side's top 8 chunks hold five of six gold names but none of the edges; the "
     "GraphRAG subgraph holds every gold item with the edge that makes it an answer."),
    ("hops", "Why Q3 needs three hops", "Then the limit of a fixed two-hop expansion.",
     svg_hp, 1560, H_HP,
     "Why Q3 needs three hops: from Bob to his projects, to his teammates, to their skills; a two-hop expansion "
     "reaches the teammates and the AWS and Python skills Bob shares with them, but not the three skills the gold "
     "set asks for."),
    ("threats", "Threat model", "With all of that drawn: where it could be attacked, and what protects it today.",
     svg_tm, 1560, H_TM,
     "Threat model: trust boundaries between the browser, the app's machine and third-party services; eleven STRIDE "
     "threats, from the missing access control to OpenAI calls with no budget or rate limit, each marked on the part "
     "it affects."),
    ("evaluation", "The comparison", "Then what the benchmark measures, and what our checks found.",
     svg_ev, 1560, H_EV,
     "The comparison: six questions run through both pipelines and scored by substring recall; what the benchmark "
     "cannot show, what a fair version adds, and our offline checks with a table of edge facts each set-up retrieves."),
    ("recommended", "The recommended architecture", "Finally: the design an FDE would build, with the 2.5 decision each numbered part answers.",
     svg_rc, 1560, H_RC,
     "The recommended architecture: the graph built from HR, project, decision and document systems through connectors, reviewed LLM extraction and entity resolution into a graph database with provenance, dates and permissions; questions routed by type and linked to node IDs, answered through templates, text-to-Cypher or hybrid retrieval, traversed with the asker's permissions, and answered by an approved model with cited node and edge IDs; governance and evaluation alongside."),
]
FDE = Path(__file__).with_name("fde_2c.html").read_text(encoding="utf-8")
for tok in ("text-embedding-3-small", "gpt-4o-mini", "top-k", "re-run", "2-hop", "3-hop", "multi-hop",
            "full-context", "zero-trust", "Zero-Trust", "WORKED_ON", "USED_TOOL", "DECISION_FOR", "HAS_SKILL"):
    FDE = FDE.replace(tok, f'<span class="nw">{tok}</span>')


def card_table(m):
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th>(.*?)</th>", m.group(0), re.S)]

    def row(r):
        cols = iter(heads)
        return re.sub(r"<td>", lambda _: f'<td data-h="{escape(next(cols, ""))}">', r.group(0))
    return re.sub(r"<tr><td>.*?</tr>", row, m.group(0), flags=re.S)


FDE = re.sub(r'<table class="qt[^"]*">.*?</table>', card_table, FDE, flags=re.S)
FDE_NAV = [("fde-mindset", "2.1", "How an FDE reads this brief"), ("fde-brief", "2.2", "The brief, phrase by phrase"),
           ("fde-people", "2.3", "Who to talk to"), ("fde-questions", "2.4", "Questions to ask"),
           ("fde-decisions", "2.5", "Decision trace"), ("fde-assumptions", "2.6", "Hidden assumptions"),
           ("fde-stress", "2.7", "Checking the comparison"), ("fde-plan", "2.8", "Engagement steps"),
           ("fde-diagrams", "2.9", "Diagrams and questions"), ("fde-takeaways", "2.10", "What to take away")]
nav = ('<nav aria-label="Contents">'
       '<div class="grp"><span class="gl">Part 1</span><span class="pills"><a href="#requirement">The requirement</a>'
       '</span></div><div class="grp"><span class="gl">Part 2 · FDE analysis</span><span class="pills">'
       + "".join(f'<a href="#{a}"><b>{n}</b>{escape(t)}</a>' for a, n, t in FDE_NAV) + "</span></div>"
       '<div class="grp"><span class="gl">Part 3 · Architecture</span><span class="pills">'
       + "".join(f'<a href="#{f[0]}"><b>{i}</b>{escape(f[1])}</a>' for i, f in enumerate(FIGS, 1))
       + "</span></div></nav>")
PART3 = """<section class="prose part" id="part3">
  <p class="partno">Part 3</p>
  <h2 class="parth">The architecture it led to</h2>
  <p class="lede">Eleven diagrams in the order a design is reasoned out: scope, parts, the data, its flow, the code
    itself, behaviour, what each side sees, the limits of the expansion, risk and the evidence, then the design an FDE would build instead. Each answers a group
    of the questions above (see 2.9).</p>
</section>"""
PFX = {"context": "cx", "architecture": "ar", "schema": "sc", "dataflow": "df", "design": "ds", "sequence": "sq",
       "contexts": "cq", "hops": "hp", "threats": "tm", "evaluation": "ev", "recommended": "rc"}
parts = []
for i, (a, t, why, body_svg, w, h, aria) in enumerate(FIGS, 1):
    parts.append(f"""<section id="{a}">
  <h2><span class="num">{i}</span>{escape(t)}</h2>
  <p class="cap"><span class="why">Why here:</span> {escape(why)}</p>
</section>
<figure>
  <div class="scroll">
  <svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(aria)}">
{defs(PFX[a])}
{body_svg}
  </svg>
  </div>
</figure>""")
body = FDE + "\n" + PART3 + "\n" + "\n".join(parts)
CSS = r"""  :root {
    --bg: #fbfaf7; --surface: #ffffff; --text: #1f2328; --muted: #5d6470; --border: #e3e0d8;
    --accent: #2f5fb3; --accent-soft: #e9f0fb; --good: #1d7a46; --good-soft: #e6f4ec;
    --warn: #9a5b00; --warn-soft: #fbf1e0; --bad: #b3261e; --bad-soft: #fbe9e7; --violet: #6a4bb3; --violet-soft: #f0ebfa;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #16181c; --surface: #1d2026; --text: #e7e9ee; --muted: #a2a9b5; --border: #2e333c;
      --accent: #8fb2f0; --accent-soft: #1f2a3d; --good: #6fcf97; --good-soft: #1b2e24;
      --warn: #f0b860; --warn-soft: #33291a; --bad: #f28b82; --bad-soft: #3a2220; --violet: #b9a3f0; --violet-soft: #272236;
    }
  }
  :root[data-theme="dark"] {
    --bg: #16181c; --surface: #1d2026; --text: #e7e9ee; --muted: #a2a9b5; --border: #2e333c;
    --accent: #8fb2f0; --accent-soft: #1f2a3d; --good: #6fcf97; --good-soft: #1b2e24;
    --warn: #f0b860; --warn-soft: #33291a; --bad: #f28b82; --bad-soft: #3a2220; --violet: #b9a3f0; --violet-soft: #272236;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.5 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
  header { max-width: 1560px; margin: 0 auto; padding: 28px 16px 8px; }
  .eyebrow { color: var(--muted); font-size: 13px; letter-spacing: .06em; text-transform: uppercase; margin: 0 0 6px; }
  h1 { font-size: 28px; line-height: 1.2; margin: 0 0 6px; }
  .src { color: var(--muted); font-size: 14.5px; margin: 0; }
  .src a { color: var(--accent); }
  figure { max-width: 1560px; margin: 12px auto 32px; padding: 0 16px; }
  .scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); padding: 10px; }
  svg { display: block; width: 100%; min-width: 1100px; height: auto; color: var(--text); }
  svg text { font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
  .t { font-size: 14.5px; font-weight: 650; fill: currentColor; }
  .s { font-size: 12.5px; fill: var(--muted); }
  .m { font-size: 12px; fill: var(--muted); }
  .mf { font-size: 12px; font-weight: 650; fill: currentColor; font-family: Consolas, Menlo, monospace; }
  .tag { font-size: 11px; fill: var(--muted); font-family: Consolas, Menlo, monospace; }
  .h { font-size: 13.5px; font-weight: 750; letter-spacing: .07em; fill: currentColor; }
  .hs { font-size: 12.5px; fill: var(--muted); }
  .lbl { font-size: 12px; font-style: italic; fill: var(--muted); }
  .lblc { font-size: 12px; font-style: italic; fill: var(--violet); }
  .pt { font-size: 12.5px; font-weight: 600; fill: currentColor; }
  .bx { fill: var(--bg); stroke: currentColor; stroke-opacity: .45; stroke-width: 1.2; }
  .dt { fill: var(--warn-soft); stroke: var(--warn); stroke-opacity: .6; stroke-width: 1.2; }
  .nd { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.4; }
  .lp { fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.3; stroke-dasharray: 5 4; }
  .pc { fill: var(--good-soft); stroke: var(--good); stroke-width: 1.4; }
  .cy { fill: var(--surface); stroke: var(--good); stroke-width: 1.3; }
  .cyt { fill: var(--good-soft); stroke: var(--good); stroke-width: 1.3; }
  .cf { fill: var(--bg); stroke: currentColor; stroke-opacity: .3; stroke-width: 1.1; stroke-dasharray: 3 3; }
  .ep { fill: var(--bg); stroke: currentColor; stroke-opacity: .55; stroke-width: 1.3; }
  .st { fill: var(--bg); stroke: var(--accent); stroke-opacity: .7; stroke-width: 1.2; }
  .ex { fill: var(--bg); stroke: currentColor; stroke-opacity: .35; stroke-width: 1.1; }
  .nt { fill: var(--warn-soft); stroke: var(--warn); stroke-opacity: .5; stroke-width: 1.1; }
  .ct { fill: var(--bg); stroke: currentColor; stroke-opacity: .35; stroke-width: 1.1; }
  .lg { fill: none; stroke: currentColor; stroke-opacity: .25; stroke-width: 1; }
  .pl { fill: var(--surface); stroke: currentColor; stroke-opacity: .6; stroke-width: 1.3; }
  .dm { fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.3; }
  .dmt { font-size: 12px; font-weight: 650; fill: var(--violet); font-family: Consolas, Menlo, monospace; }
  .llm { fill: var(--warn-soft); stroke: var(--warn); stroke-width: 1; }
  .llmt { font-size: 11px; font-weight: 700; fill: var(--warn); }
  .wb { fill: var(--bad-soft); stroke: var(--bad); stroke-width: 1.1; }
  .wbt { font-size: 11px; font-weight: 700; fill: var(--bad); }
  .dot { fill: var(--accent); }
  .ln { fill: none; stroke: currentColor; stroke-opacity: .6; stroke-width: 1.5; }
  .lnc { fill: none; stroke: var(--violet); stroke-width: 1.5; stroke-dasharray: 6 4; }
  .ah { fill: currentColor; fill-opacity: .7; }
  .ahc { fill: var(--violet); }
  .bnd { fill: none; stroke: currentColor; stroke-opacity: .4; stroke-width: 1.3; stroke-dasharray: 8 5; }
  .bndc { fill: var(--accent-soft); fill-opacity: .35; stroke: var(--accent); stroke-opacity: .6; stroke-width: 1.3;
    stroke-dasharray: 8 5; }
  .pa { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.3; }
  .chip { fill: var(--surface); stroke: var(--accent); stroke-width: 1.2; }
  .cht { font-size: 12.5px; font-weight: 650; fill: currentColor; }
  .lnd { fill: none; stroke: currentColor; stroke-opacity: .5; stroke-width: 1.3; stroke-dasharray: 4 4; }
  section { max-width: 1560px; margin: 0 auto; padding: 0 16px; }
  h2 { font-size: 20px; margin: 22px 0 2px; }
  h2 .num { color: var(--accent); margin-right: 6px; }
  .cap { color: var(--muted); font-size: 14.5px; margin: 0; }
  .t2 { font-size: 13.5px; font-weight: 650; fill: currentColor; }
  .t3 { font-size: 12.5px; font-weight: 650; fill: currentColor; }
  .mi { font-size: 11.5px; font-style: italic; fill: var(--good); }
  .lbs { font-size: 11.5px; font-style: italic; fill: var(--muted); }
  .msg { font-size: 12.5px; fill: currentColor; }
  .pm { font-size: 12px; fill: currentColor; font-family: Consolas, Menlo, monospace; }
  .rl { font-size: 11px; font-weight: 750; letter-spacing: .06em; fill: var(--muted); }
  .pr { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.4; }
  .prl { stroke: var(--accent); stroke-opacity: .6; stroke-width: 1; fill: none; }
  .pid { font-size: 11.5px; font-weight: 750; fill: var(--accent); }
  .ee { fill: var(--surface); stroke: currentColor; stroke-opacity: .75; stroke-width: 1.8; }
  .dupl { stroke: currentColor; stroke-opacity: .75; stroke-width: 1.5; }
  .dsf { fill: var(--good-soft); }
  .dsl { fill: none; stroke: var(--good); stroke-width: 1.5; }
  .dsid { font-size: 12.5px; font-weight: 750; fill: var(--good); }
  .cn { fill: var(--surface); stroke: var(--violet); stroke-width: 1.5; }
  .cnt { font-size: 12px; font-weight: 750; fill: var(--violet); }
  .life { fill: none; stroke: currentColor; stroke-opacity: .35; stroke-width: 1.2; stroke-dasharray: 5 5; }
  .act { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1; }
  .frame { fill: none; stroke: currentColor; stroke-opacity: .4; stroke-width: 1.1; }
  .frtab { fill: var(--bg); stroke: currentColor; stroke-opacity: .4; stroke-width: 1.1; }
  .frt { font-size: 11.5px; font-weight: 700; fill: currentColor; }
  .ret { fill: none; stroke: currentColor; stroke-opacity: .55; stroke-width: 1.3; stroke-dasharray: 5 4; }
  .lnr { fill: none; stroke: var(--bad); stroke-width: 1.6; }
  .ahr { fill: var(--bad); }
  .tb { fill: none; stroke: var(--bad); stroke-opacity: .7; stroke-width: 1.6; stroke-dasharray: 9 5; }
  .tbl { fill: none; stroke: var(--bad); stroke-opacity: .7; stroke-width: 1.6; stroke-dasharray: 9 5; }
  .tbt { font-size: 12.5px; font-weight: 750; fill: var(--bad); }
  .sysb { fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.1; }
  .humb { fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.1; }
  .repb { fill: var(--good-soft); stroke: var(--good); stroke-width: 1.1; }
  nav { max-width: 1560px; margin: 14px auto 0; padding: 0 16px; }
  nav .grp { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; margin: 0 0 10px; }
  nav .gl { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
    width: 200px; }
  nav .pills { display: flex; flex-wrap: wrap; gap: 8px; flex: 1 1 360px; }
  .callout, blockquote.req { max-width: 1000px; }
  .prose p, .prose li { max-width: 96ch; }
  .prose p { margin: 8px 0; }
  .prose a { color: var(--accent); }
  .part { margin-top: 36px; }
  .partno { color: var(--accent); font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    margin: 0 !important; }
  h2.parth { font-size: 25px; margin: 2px 0 6px; }
  .lede { font-size: 16.5px; }
  h3 { font-size: 19.5px; margin: 34px 0 6px; }
  h3 .sn { color: var(--accent); margin-right: 8px; }
  h4 { font-size: 15.5px; margin: 22px 0 4px; }
  h4 .who { font-weight: 400; color: var(--muted); font-size: 13.5px; margin-left: 8px; }
  blockquote.req { margin: 12px 0 8px; padding: 12px 20px; background: var(--surface); border: 1px solid var(--border);
    border-left: 4px solid var(--accent); border-radius: 10px; }
  .reqt { font-size: 17px; font-weight: 700; margin: 4px 0 6px !important; }
  .reqh { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
    margin: 12px 0 0 !important; }
  .callout { margin: 14px 0; padding: 8px 16px; background: var(--surface); border: 1px solid var(--border);
    border-left: 4px solid var(--violet); border-radius: 10px; }
  .callout.warnc { border-left-color: var(--warn); }
  .callout.goodc { border-left-color: var(--good); }
  .callout ul, .callout ol { margin: 4px 0 8px; padding-left: 22px; }
  .legend { font-size: 14px; color: var(--muted); line-height: 1.9; }
  .habits li, .steps li { margin: 7px 0; }
  .tw { overflow-x: auto; margin: 10px 0 16px; border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface); }
  table.qt { border-collapse: collapse; width: 100%; min-width: 820px; font-size: 14.5px; line-height: 1.45; }
  table.qt th { text-align: left; font-size: 11.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); background: var(--bg); padding: 8px 12px; border-bottom: 1px solid var(--border); }
  table.qt td { vertical-align: top; padding: 9px 12px; border-bottom: 1px solid var(--border); }
  table.qt tr:last-child td { border-bottom: 0; }
  table.q3 th:nth-child(1) { width: 38%; }
  table.q3 th:nth-child(2) { width: 26%; }
  table.dt5 { min-width: 1120px; }
  table.dt5 th:nth-child(1) { width: 12%; }
  table.dt5 th:nth-child(5) { width: 31%; }
  .tg { display: inline-block; font-size: 11.5px; font-weight: 650; line-height: 1.6; padding: 0 7px; border-radius: 999px;
    white-space: nowrap; vertical-align: 1px; }
  .tg.doc { color: var(--good); background: var(--good-soft); }
  .tg.code { color: var(--accent); background: var(--accent-soft); }
  .tg.asm { color: var(--warn); background: var(--warn-soft); }
  .first { color: var(--warn); font-weight: 700; }
  code { font-family: Consolas, Menlo, monospace; font-size: .9em; background: var(--bg); border: 1px solid var(--border);
    border-radius: 4px; padding: 0 4px; }
  nav a { padding: 6px 11px; border: 1px solid var(--border); border-radius: 999px; background: var(--surface);
    color: var(--text); text-decoration: none; font-size: 13.5px; }
  nav a:hover { border-color: var(--accent); }
  nav a b { color: var(--accent); margin-right: 5px; }
  .why { color: var(--accent); font-weight: 600; }
  .notebg { fill: var(--surface); fill-opacity: .9; }
  .aho { fill: none; stroke: currentColor; stroke-opacity: .75; stroke-width: 1.3; }
  .altsep { fill: none; stroke: currentColor; stroke-opacity: .45; stroke-width: 1.1; stroke-dasharray: 6 4; }
  @media (max-width: 560px) { h1 { font-size: 23px; } }
  .legend .li { display: inline-block; margin-right: 14px; }
  .nw { white-space: nowrap; }
  @media (max-width: 560px) {
    nav .gl { width: auto; }
    .prose table.qt thead { display: none; }
    .prose table.qt, .prose table.qt tbody, .prose table.qt tr, .prose table.qt td { display: block; min-width: 0;
      width: auto; }
    .prose table.qt tr { border-bottom: 1px solid var(--border); padding: 6px 0; }
    .prose table.qt tr:last-child { border-bottom: 0; }
    .prose table.qt td { border: 0; padding: 3px 12px; }
    .prose table.qt td::before { content: attr(data-h); display: block; font-size: 11px; font-weight: 700;
      letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
  }
  .tg.chk { color: var(--violet); background: var(--violet-soft); }
  .prose p.note { font-size: 14px; color: var(--muted); margin-top: -6px; }
"""
page = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>2C: Brief to Architecture</title>\n<style>\n" + CSS + "\n</style>\n</head>\n<body>\n<header>\n"
        "  <p class=\"eyebrow\">Requirement → FDE analysis → architecture · The Gen Academy · Week 2, project 2C</p>\n"
        "  <h1>GraphRAG for Organizational Knowledge</h1>\n"
        "  <p class=\"src\">Drawn from the code at commit <a href=\"https://github.com/The-Gen-Academy/"
        "2C-Graph-RAG-for-Organizational-Knowledge/tree/b9bae00\">b9bae00</a> and the "
        "<a href=\"https://docs.google.com/document/d/16uvBJFgv2KpE8IsIEwYD_xAbFMgSxZqA/edit\">solution kit</a>.</p>\n"
        "</header>\n" + nav + "\n" + body + "\n</body>\n</html>\n")
OUT.write_text(page, encoding="utf-8")
print("written:", OUT, len(FIGS), "figures")
for w in warnings:
    print("WARN", w)
