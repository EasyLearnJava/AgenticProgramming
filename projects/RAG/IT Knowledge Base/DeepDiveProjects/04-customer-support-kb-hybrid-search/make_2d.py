"""Writes the requirement, FDE analysis and architecture page of The Gen Academy's 2D Customer Support
Knowledge Base with Hybrid Search as one self-contained HTML file. Reads Parts 1 and 2 from fde_2d.html beside it.
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


def ent(x, y, w, h, eid, title, sub="", dup=False, cls="ee"):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="{cls}"/>')
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


def pills(x, y, w, rows, title):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{44 + 30 * len(rows)}" rx="10" class="cf"/>')
    text(x + 16, y + 22, title, "t2")
    for i, (t, s_) in enumerate(rows):
        yy = y + 36 + 30 * i
        out.append(f'<rect x="{x + 16}" y="{yy}" width="96" height="24" rx="12" class="pl"/>')
        text(x + 64, yy + 16, t, "pt", "middle")
        text(x + 124, yy + 16, s_, "m")
        fits(s_, w - 140, "m", title)


# ================================================================ 1 · system context
out, P = [], "cx"
out.append('<rect x="470" y="28" width="700" height="440" rx="14" class="bnd"/>')
text(1158, 48, "system boundary: the app, its data files and the indexes it builds in memory", "lbs", "end")
box(605, 60, 210, 96, "data/*.json", ["25 entries: 10 FAQs, 10", "ticket notes, 5 manuals", "typed by hand"], cls="dt")
box(510, 200, 400, 170, "CloudSync Pro support bot", [
    "app.py (Streamlit) or eval.py (benchmark)", "BM25 + FAISS over the 25 entries",
    "local embeddings: all-MiniLM-L6-v2", "gate: answer, LLM judge, or escalate",
    "LangGraph · LangChain; LLM calls go to OpenAI"], cls="nd")
fl("M710 156 V198")
label(718, 182, "entries, at start-up")
person(160, 196, "Customer", "or a tester")
fl("M196 222 H508")
label(352, 214, "a question", "middle")
fl("M508 250 H196")
label(352, 266, "an answer, or “an agent will reach out”", "middle")
person(160, 330, "Support agent", "not connected")
out.append('<path d="M508 354 H196" class="lnd"/>')
label(352, 346, "escalation: nothing is sent", "middle")
box(1240, 170, 300, 100, "OpenAI API", ["gpt-4o-mini: judge and answer", "receives the question and the",
                                       "candidate entries' text"], cls="ex")
box(1240, 290, 300, 70, "Hugging Face Hub", ["all-MiniLM-L6-v2, by name"], cls="ex")
box(1240, 380, 300, 70, "PyPI", ["10 packages, 3 with no upper bound"], cls="ex")
fl("M912 212 H1238")
label(1062, 205, "question, candidate texts", "middle")
fl("M1238 242 H912")
label(1062, 235, "YES / NO, reply", "middle")
fl("M1238 325 H912")
label(1062, 318, "model weights, first run", "middle")
fl("M1238 415 H880 V372")
label(1062, 408, "packages, at install", "middle")
svg_ctx, H_CTX = done(490)

# ================================================================ 2 · high-level architecture
out, P = [], "ar"
out.append('<rect x="220" y="24" width="980" height="520" rx="14" class="bndc"/>')
text(240, 48, "ONE PYTHON PROCESS · app.py (Streamlit) or eval.py · indexes in memory", "h")
pills(500, 66, 680, [("retrieve", "hybrid search, then a cosine score for every candidate; top_sim = best"),
                     ("grade", "≥ 0.55 answer · < 0.35 escalate · in between: LLM judge, YES or NO"),
                     ("answer", "LLM reply from all candidates, cites [id]; INSUFFICIENT_CONTEXT → escalate"),
                     ("escalate", "fixed message naming the closest title; no LLM, nothing sent")],
      "Bot (build_bot) · a LangGraph workflow (bot.py)")
box(240, 290, 220, 106, "app.py · eval.py", ["Streamlit chat with a trace,", "or the 20-case benchmark",
                                             "(eval_set.py)"], cls="nd")
box(500, 290, 340, 150, "retriever.py", ["BM25Retriever, k = 4 (whitespace tokens)", "FAISS, k = 4 (all-MiniLM-L6-v2)",
                                         "EnsembleRetriever: RRF, 0.4 / 0.6", "score_query: cosine per candidate"],
    cls="ep")
box(880, 290, 300, 106, "knowledge_base.py", ["load_documents(): 25 entries", "page_content = title + content",
                                              "metadata: id, source, title"], cls="ep")
fl("M350 288 V150 H498", "both")
label(358, 200, "question,")
label(358, 214, "state")
fl("M670 232 V288", "both")
label(678, 266, "query / scored candidates")
fl("M878 343 H842")
person(110, 300, "Customer", "or a tester")
fl("M146 328 H238")
label(182, 320, "question", "middle")
fl("M238 352 H146")
label(182, 368, "answer", "middle")
box(1290, 66, 250, 164, "OpenAI API", ["gpt-4o-mini, temperature 0", "judge: borderline only",
                                       "answer: every answer route"], cls="ex")
fl("M1180 150 H1288", "both")
label(1245, 142, "0–2 calls", "middle")
box(1290, 436, 250, 80, "data/*.json (on disk)", ["faqs 10 · tickets 10 · manuals 5"], cls="dt")
fl("M1288 476 H1240 V343 H1182")
label(1248, 420, "JSON")
box(500, 580, 340, 70, "Hugging Face Hub", ["all-MiniLM-L6-v2 weights, first run"], cls="ex")
fl("M670 578 V442")
label(678, 562, "model weights")
svg_ar, H_AR = done(670)

# ================================================================ 3 · the knowledge base and the benchmark
out, P = [], "kb"
header(20, 28, "THE KNOWLEDGE BASE · 25 entries, one document each")
TESTED = {"faq-001": 2, "faq-002": 2, "faq-003": 1, "faq-004": 1, "faq-005": 1, "faq-007": 1, "faq-008": 1,
          "faq-009": 1, "faq-010": 1, "ticket-1042": 1, "ticket-1108": 1, "ticket-1175": 1, "ticket-1356": 1,
          "ticket-1521": 1, "manual-install": 1, "manual-api": 1}
GROUPS = [("FAQs (10) · written for customers", 54, [f"faq-{i:03d}" for i in range(1, 11)]),
          ("Ticket resolutions (10) · notes written by agents", 184,
           ["ticket-1042", "ticket-1108", "ticket-1175", "ticket-1230", "ticket-1289", "ticket-1314",
            "ticket-1356", "ticket-1402", "ticket-1478", "ticket-1521"]),
          ("Manual sections (5)", 314, ["manual-install", "manual-selective-sync", "manual-api",
                                        "manual-admin-sso", "manual-cli"])]
for title, y0, ids_ in GROUPS:
    text(20, y0, title, "t3")
    for i, d in enumerate(ids_):
        x, y = 20 + (i % 5) * 148, y0 + 12 + (i // 5) * 50
        n = TESTED.get(d, 0)
        out.append(f'<rect x="{x}" y="{y}" width="140" height="40" rx="7" class="{"repb" if n else "ex"}"/>')
        text(x + 10, y + 25, d, "m")
        if n > 1:
            text(x + 130, y + 25, f"×{n}", "m", "end")
text(20, 420, "Green: an entry the benchmark expects as the top result (16 of 25). The other 9 are never tested.", "s")
out.append('<rect x="20" y="436" width="732" height="124" rx="9" class="nt"/>')
text(36, 458, "Ticket notes are written for agents, and some expire", "t3")
for i, (q, why) in enumerate((
        ("ticket-1289: “…refund the second charge and add a note to the account.”", "an instruction to an agent"),
        ("ticket-1175: “The customer must use one of their saved backup codes…”", "third person: about the customer"),
        ("ticket-1042: “Affects desktop client versions 4.8.0 through 4.8.3.”", "goes stale with a release"))):
    text(36, 484 + 24 * i, q, "m")
    text(736, 484 + 24 * i, why, "lbs", "end")
header(800, 28, "THE BENCHMARK · 20 questions (eval_set.py)")
CASES = ["F"] * 11 + ["T"] * 5 + ["M"] * 2 + ["E"] * 2
CLS = {"F": "nd", "T": "dt", "M": "vio", "E": "wb"}
for i, c in enumerate(CASES):
    x, y = 800 + (i % 10) * 74, 50 + (i // 10) * 50
    out.append(f'<rect x="{x}" y="{y}" width="66" height="40" rx="7" class="{CLS[c]}"/>')
    text(x + 33, y + 25, str(i + 1), "t3", "middle")
for i, (c, lab) in enumerate((("F", "FAQ answer (11)"), ("T", "ticket answer (5)"), ("M", "manual answer (2)"),
                              ("E", "should escalate (2)"))):
    x = 800 + i * 186
    out.append(f'<rect x="{x}" y="160" width="18" height="14" rx="3" class="{CLS[c]}"/>')
    text(x + 26, 172, lab, "m")
box(800, 196, 740, 104, "What a case must show to pass (eval.py)", [
    "answer cases (18): the bot answers, the top entry is the expected one, and the reply contains the expected",
    "phrase when one is set (17 of 18), e.g. “link”, “Security”, “5 GB”; each restates or paraphrases an entry",
    "escalate cases (2): the bot escalates (“Can CloudSync integrate with Salesforce?”, “dark mode”)"], cls="ep")
box(800, 320, 740, 200, "Not in the benchmark", [
    "requests to act on an account or make an exception: refunds, access, cancelling for the customer",
    "complaints, angry or urgent customers, requests to talk to a human",
    "other languages, typos, several questions in one message",
    "follow-up turns that depend on the previous answer",
    "prompt injection and attempts to talk the bot into promises",
    "questions the knowledge base only half answers, or answers with an outdated fix",
    "a realistic share of questions that should escalate (here 2 of 20)"], cls="nt", step=20)
svg_kb, H_KB = done(580)

# ================================================================ 4 · data flow (level 1, Gane-Sarson)
out, P = [], "df"
store(420, 20, 300, 50, "D1", "data/*.json", ["25 entries"])
proc(470, 110, 200, 92, "P1", "Load and index", ["knowledge_base.py,", "retriever.py (start-up)"])
fl("M570 70 V108")
label(578, 94, "entries", cls="lbs")
ent(760, 126, 220, 60, "E3", "Hugging Face Hub", "model download")
fl("M758 156 H672")
label(715, 148, "weights", "middle", "lbs")
store(330, 240, 250, 50, "D2", "BM25 index (memory)", ["whitespace tokens"])
store(600, 240, 250, 50, "D3", "FAISS index (memory)", ["384-d vectors"])
fl("M500 202 V238")
fl("M640 202 V238")
proc(470, 340, 200, 100, "P3", "Retrieve and score", ["embed the question;", "top 4 + top 4, RRF; cosine"])
fl("M540 290 V338")
label(548, 322, "BM25 top 4", cls="lbs")
fl("M650 290 V338")
label(658, 322, "FAISS top 4", cls="lbs")
ent(120, 200, 180, 60, "E1", "Customer", "or tester")
proc(170, 340, 190, 100, "P2", "Chat UI or eval", ["app.py: chat + trace", "eval.py: a line per case"])
fl("M180 260 V338")
label(172, 318, "question", "end", "lbs")
fl("M262 338 V262")
label(270, 318, "answer, trace (incl.", cls="lbs")
label(270, 332, "ticket-note text)", cls="lbs")
fl("M362 390 H468")
label(415, 382, "question", "middle", "lbs")
proc(790, 340, 200, 100, "P4", "Grade", ["0.55 / 0.35 cut-offs;", "judge in between"])
fl("M672 390 H788")
label(730, 368, "question,", "middle", "lbs")
label(730, 382, "candidates, top_sim", "middle", "lbs")
ent(1330, 280, 200, 330, "E2", "OpenAI API", "gpt-4o-mini")
proc(1070, 340, 200, 100, "P5", "Answer", ["all candidates,", "cite [id]"])
fl("M992 390 H1068")
label(1030, 368, "question +", "middle", "lbs")
label(1030, 382, "candidates", "middle", "lbs")
fl("M1272 378 H1328")
label(1300, 370, "prompt", "middle", "lbs")
fl("M1328 404 H1272")
label(1300, 420, "reply", "middle", "lbs")
fl("M870 338 V296 H1328")
label(1110, 288, "question + best entry", "middle", "lbs")
fl("M1328 318 H910 V338")
label(1030, 334, "YES / NO", "middle", "lbs")
proc(790, 520, 200, 92, "P6", "Escalate", ["fixed message,", "closest title"])
fl("M890 442 V518")
label(898, 474, "question +", cls="lbs")
label(898, 488, "closest title", cls="lbs")
fl("M1170 442 V566 H992")
label(1080, 544, "question + closest title", "middle", "lbs")
label(1080, 558, "(INSUFFICIENT_CONTEXT)", "middle", "lbs")
fl("M788 566 H310 V442")
label(550, 558, "handoff message + state", "middle", "lbs")
fl("M1240 442 V680 H230 V442")
label(735, 672, "answer + state (all candidates' text)", "middle", "lbs")
store(10, 600, 200, 50, "D4", "session history", ["Streamlit, per session"])
fl("M190 442 V598", "both")
ent(1030, 600, 200, 50, "E4", "Support agent", "no flow reaches them", cls="eeX")
out.append('<path d="M992 590 H1028" class="lnd"/>')
svg_dfd, H_DFD = done(710)

# ================================================================ 5 · detailed design
out, P = [], "ds"
FILES = [
    ("data/*.json", ["faqs 10 · tickets 10 · manuals 5; fields id, source, title, content"], [8]),
    ("knowledge_base.py", ["load_documents(): one Document per entry; page_content = title + content",
                           "metadata: id, source, title"], []),
    ("retriever.py", ["EMBED_MODEL = sentence-transformers/all-MiniLM-L6-v2, loaded by name; TOP_K = 4",
                      "BM25Retriever.from_documents: default tokens = text.split()",
                      "FAISS.from_documents; EnsembleRetriever weights 0.4 / 0.6 (RRF)",
                      "score_query: re-embeds the candidates, cosine to the query"], [12, 3, 2, 1]),
    ("bot.py", ["HIGH_CONF 0.55 · LOW_CONF 0.35 · gpt-4o-mini, temperature 0",
                "retrieve: re-sort candidates by cosine; top_sim = the best",
                "grade: judge only between the cut-offs, on the best candidate's text",
                "answer: all candidates, cite [id]; INSUFFICIENT_CONTEXT → escalate",
                "escalate: fixed message naming the closest title"], [7, 6, 5, 4]),
    ("eval_set.py · eval.py", ["20 cases (18 answer, 2 escalate); must_include phrases (17 of 18 cases)",
                               "“FCR” = passes ÷ 20; a correct escalation passes; exit 1 below 70%"], [9]),
    ("app.py", ["Streamlit chat; sidebar API-key box sets os.environ",
                "trace shows every candidate's full text; history in the session only"], [11, 10]),
    ("requirements.txt", ["10 packages; 3 with no upper bound; no lock file"], [12]),
]
y = 20
for title, lines, notes in FILES:
    h = 34 + 16 * len(lines) + 8
    box(20, y, 760, h, title, lines, cls="nd" if title.endswith("py") else "ep", warn=notes)
    y += h + 12
H_D5 = y
NOTES5 = [
    ("The gate's score is the best cosine over the candidates, always the best over all 25 entries, so BM25",
     "never reaches the gate; all candidates are kept and re-sorted, so the RRF weights change nothing."),
    ("Default BM25 tokens keep case and punctuation: “CMEK”, “file.shared” and “2fa” score zero",
     "on every entry (our check)."),
    ("In short questions the product name lifts cosine by about 0.2–0.4; “Can CloudSync integrate",
     "with Salesforce?” reaches the answer zone at 0.647 (our check)."),
    ("Cut-offs “tuned against the eval set”; the README the docstring points to does not exist.", ""),
    ("The judge sees only the best candidate; the answer step sees all of them.", ""),
    ("Citations are not checked; only the answer prompt's rules stop a reply promising a refund.", ""),
    ("escalate creates no ticket and contacts no one, yet tells the customer an agent will reach out.", ""),
    ("Ticket notes are written for agents and some are version-specific, yet all are quotable.", ""),
    ("“FCR” counts a correct escalation as resolved; 18 of 20 cases restate or paraphrase an entry.", ""),
    ("The trace shows customers the full text of every candidate, internal ticket notes included.", ""),
    ("A key typed in the sidebar sets os.environ for the whole process: later visitors use it too.", ""),
    ("No lock file and 3 packages with no upper bound; the model is fetched by name, no pinned revision.", ""),
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

# ================================================================ 6 · sequence: one question, three routes
out, P = [], "sq"
LIFE = [("app.py", "or eval.py", 110), ("bot", "LangGraph", 420), ("retriever", "BM25 + FAISS, local", 800),
        ("OpenAI", "gpt-4o-mini", 1180)]
SEQ_END = 760
for name_, sub, x in LIFE:
    out.append(f'<rect x="{x - 90}" y="24" width="180" height="50" rx="8" class="ep"/>')
    text(x, 46, name_, "t2", "middle")
    text(x, 63, sub, "m", "middle")
    out.append(f'<path d="M{x} 74 V{SEQ_END}" class="life"/>')
X = {n: x for n, _, x in LIFE}
for who, y1, y2 in (("app.py", 106, 742), ("bot", 116, 736), ("retriever", 144, 182), ("retriever", 200, 238),
                    ("OpenAI", 370, 408), ("OpenAI", 520, 558)):
    out.append(f'<rect x="{X[who] - 6}" y="{y1}" width="12" height="{y2 - y1}" class="act"/>')


def msg(a, b, y, s, ret=False, n=None, lx=None):
    x1, x2 = X[a] + (6 if X[b] > X[a] else -6), X[b] + (-6 if X[b] > X[a] else 6)
    fl(f"M{x1} {y} H{x2}", "ret" if ret else "ln")
    if lx is None:
        text((x1 + x2) / 2, y - 7, s, "msg" if not ret else "lbl", "middle")
    else:
        text(lx, y - 7, s, "msg" if not ret else "lbl")
    fits(s, abs(x2 - x1) + 60, "msg", "sequence")
    if n:
        out.append(f'<rect x="{X["OpenAI"] + 20}" y="{y - 13}" width="{14 + 6.6 * len(n)}" height="19" rx="9.5" '
                   f'class="llm"/>')
        text(X["OpenAI"] + 27 + 3.3 * len(n), y + 1, n, "llmt", "middle")


def self_msg(who, y, s):
    x = X[who] + 6
    out.append(f'<path d="M{x} {y} H{x + 40} V{y + 16} H{x + 2}" class="ln" marker-end="url(#{P}ar)"/>')
    text(x + 48, y + 12, s, "msg")


def frame(y1, y2, x1, x2, tab, guard, tabw=44, seps=()):
    out.append(f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" rx="6" class="frame"/>')
    out.append(f'<path d="M{x1} {y1} H{x1 + tabw} V{y1 + 14} L{x1 + tabw - 10} {y1 + 22} H{x1} Z" class="frtab"/>')
    text(x1 + 8, y1 + 15, tab, "frt")
    text(x1 + tabw + 10, y1 + 15, guard, "frt")
    for sy, sg in seps:
        out.append(f'<path d="M{x1} {sy} H{x2}" class="lnd"/>')
        text(x1 + tabw + 10, sy + 16, sg, "frt")


msg("app.py", "bot", 116, "ask(question)")
msg("bot", "retriever", 150, "retrieve: BM25 top 4 + FAISS top 4, merged by RRF")
msg("retriever", "bot", 176, "up to 8 candidates", ret=True)
msg("bot", "retriever", 206, "score_query: cosine of each candidate to the question")
msg("retriever", "bot", 232, "(entry, cosine) pairs", ret=True)
self_msg("bot", 250, "sort by cosine; top_sim = the best")
frame(290, 480, 380, 1300, "alt", "[top_sim ≥ 0.55]",
      seps=((330, "[0.35 ≤ top_sim < 0.55]"), (430, "[top_sim < 0.35]")))
text(640, 315, "answer route, no judge", "msg")
msg("bot", "OpenAI", 376, "judge: question + best candidate's text", n="1", lx=860)
msg("OpenAI", "bot", 402, "YES (answer route) or NO (escalate)", ret=True, lx=860)
text(830, 460, "escalate route: “low retrieval similarity”", "msg")
frame(496, 652, 380, 1300, "opt", "[answer route]")
msg("bot", "OpenAI", 526, "answer prompt: question + all candidates", n="2", lx=860)
msg("OpenAI", "bot", 552, "reply with [id] citations, or INSUFFICIENT_CONTEXT", ret=True, lx=830)
frame(574, 640, 400, 1280, "opt", "[reply is INSUFFICIENT_CONTEXT]")
self_msg("bot", 606, "switch to the escalate route")
frame(664, 722, 380, 1300, "opt", "[escalate route]")
self_msg("bot", 690, "fixed message, closest title; nothing sent")
msg("bot", "app.py", 736, "state: answer, decision, top_sim, scored, judge_used, …", ret=True)
text(1500, SEQ_END + 22, "solid arrow: a call · dashed, open arrow: its reply · bars: active · numbers: LLM calls",
     "m", "end")
svg_seq, H_SEQ = done(SEQ_END + 40)

# ================================================================ 7 · what the confidence gate sees
out, P = [], "gt"
header(20, 28, "WHAT THE GATE SEES · 43 queries placed by top_sim against 2D's two cut-offs")
text(20, 50, "Each dot is one query. The gate answers, asks the judge or escalates by the band the dot falls in.", "s")
GATE = [
    (0.621, True, "How do I reset my password?"), (0.473, True, "I forgot my login and can't get into my account"),
    (0.693, True, "What's the storage limit on the Plus plan?"),
    (0.497, True, "How much does the Business plan cost per user?"),
    (0.773, True, "How do I enable two-factor authentication?"),
    (0.802, True, "Can I share files with people who aren't on CloudSync?"),
    (0.806, True, "How do I cancel my subscription?"), (0.453, True, "Is there an iPhone app?"),
    (0.667, True, "How long are deleted files kept on the Free plan?"), (0.579, True, "Is my data encrypted at rest?"),
    (0.601, True, "Do you have a discount for nonprofits?"),
    (0.715, True, "My CloudSync is stuck on 'Preparing to upload' on Windows"),
    (0.674, True, "Why can't I upload a 10 GB file from the website?"),
    (0.682, True, "I got a new phone and my 2FA codes don't work anymore"),
    (0.699, True, "The desktop app crashes on launch after I updated to macOS Sonoma"),
    (0.679, True, "Where can I request a GDPR data export?"), (0.609, True, "Can I install CloudSync on Ubuntu?"),
    (0.483, True, "What are the API rate limits?"), (0.279, True, "WinFsp"), (0.394, True, "SCIM bearer token"),
    (0.516, True, "cloudsync push --resumable"), (0.112, True, "CMEK"), (0.296, True, "TOTP seed"),
    (0.275, True, "501(c)(3)"), (0.429, True, "file.shared webhook"), (0.315, True, "MDM .msi"),
    (0.194, True, "Can I install it on Ubuntu?"), (0.656, True, "How do I turn on 2fa?"),
    (0.569, True, "What happens to my data if I cancel?"), (0.651, True, "How do I fix conflict copies?"),
    (0.647, False, "Can CloudSync integrate with Salesforce?"), (0.210, False, "Is there a dark mode in the desktop app?"),
    (0.355, False, "Can it integrate with Salesforce?"),
    (0.407, False, "Is there a dark mode in the CloudSync desktop app?"),
    (0.511, False, "Can CloudSync integrate with Slack?"), (0.211, False, "Can it integrate with Slack?"),
    (0.537, False, "Does CloudSync support Kubernetes?"), (0.439, False, "What's the price of the Enterprise plan?"),
    (0.467, False, "Is CloudSync HIPAA compliant?"), (0.158, False, "Do you have a SOC 2 report?"),
    (0.201, False, "Can I pay with PayPal?"), (0.541, False, "Does CloudSync Pro work on Chromebooks?"),
    (0.157, False, "What's the weather in Paris tomorrow?")]
X0, X1 = 200, 1180
gx = lambda v: X0 + v * (X1 - X0) / 0.9  # noqa: E731
ROWY = {True: 196, False: 384}
out.append(f'<rect x="{X0}" y="96" width="{gx(0.35) - X0:.1f}" height="380" class="bE"/>')
out.append(f'<rect x="{gx(0.35):.1f}" y="96" width="{gx(0.55) - gx(0.35):.1f}" height="380" class="bJ"/>')
out.append(f'<rect x="{gx(0.55):.1f}" y="96" width="{X1 - gx(0.55):.1f}" height="380" class="bA"/>')
text((X0 + gx(0.35)) / 2, 116, "escalate, no LLM (below 0.35)", "t3", "middle")
text((gx(0.35) + gx(0.55)) / 2, 116, "LLM judge (0.35–0.55)", "t3", "middle")
text((gx(0.55) + X1) / 2, 116, "answer step, no judge (0.55 and up)", "t3", "middle")
text(20, ROWY[True] + 4, "answerable (30)", "t3")
text(20, ROWY[True] + 22, "an entry states it", "m")
text(20, ROWY[False] + 4, "not answerable (13)", "t3")
text(20, ROWY[False] + 22, "no entry states it", "m")
out.append(f'<path d="M{X0} 476 H{X1}" class="ax"/>')
for t in range(10):
    xx = gx(t / 10)
    out.append(f'<path d="M{xx:.1f} 476 V482" class="ax"/>')
    text(xx, 498, f"{t / 10:.1f}", "m", "middle")
text((X0 + X1) / 2, 520, "top_sim: best cosine similarity of the question to any entry (all-MiniLM-L6-v2)", "s",
     "middle")
placed = {True: [], False: []}
POS = {}
for v, ans, q in sorted(GATE, key=lambda r: r[0]):
    cx = gx(v)
    for off in (0, -16, 16, -32, 32, -48, 48, -64, 64):
        cy = ROWY[ans] + off
        if all((cx - px) ** 2 + (cy - py) ** 2 >= 14 ** 2 for px, py in placed[ans]):
            break
    placed[ans].append((cx, cy))
    POS[q] = (cx, cy)
    out.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="6" class="{"dA" if ans else "dU"}"/>')


def pair(q_without, q_with, lab, above=True):
    (x1, y1), (x2, y2) = POS[q_without], POS[q_with]
    lift = -54 if above else 54
    mx, my = (x1 + x2) / 2, min(y1, y2) + lift if above else max(y1, y2) + lift
    out.append(f'<path d="M{x1:.1f} {y1 + (-8 if above else 8)} Q{mx:.1f} {my} {x2:.1f} {y2 + (-8 if above else 8)}" '
               f'class="lnc" marker-end="url(#{P}arc)"/>')
    text(mx, my + (8 if above else 2), lab, "lbs", "middle")


pair("Can I install it on Ubuntu?", "Can I install CloudSync on Ubuntu?",
     "“it” → “CloudSync”: 0.194 → 0.609 (benchmark case 17)")
pair("Can it integrate with Salesforce?", "Can CloudSync integrate with Salesforce?",
     "“it” → “CloudSync”: 0.355 → 0.647 (benchmark case 19)", above=False)
for (cnt_a, cnt_u), (lo, hi) in zip(((6, 5), (7, 7), (17, 1)), ((0, 0.35), (0.35, 0.55), (0.55, 0.9))):
    xm = (gx(lo) + gx(hi)) / 2
    text(xm, 286, f"{cnt_a} of 30", "s", "middle")
    text(xm, 462, f"{cnt_u} of 13", "s", "middle")
out.append('<rect x="1220" y="96" width="320" height="296" rx="9" class="nt"/>')
text(1236, 120, "Separation on the same 43 queries (AUC)", "t3")
text(1236, 138, "chance a random answerable query scores", "m")
text(1236, 152, "higher than a random unanswerable one", "m")
BX0, BX1 = 1236, 1520
bx = lambda a: BX0 + (a - 0.5) / 0.5 * (BX1 - BX0)  # noqa: E731
for i, (lab, a, lo, hi, cls) in enumerate((("cosine: 2D's gate", 0.759, 0.603, 0.890, "barG"),
                                           ("cosine, brand name removed", 0.874, 0.759, 0.969, "barA"),
                                           ("BM25, normalized tokens", 0.892, 0.774, 0.977, "barA"),
                                           ("cross-encoder reranker", 0.941, 0.862, 0.992, "barA"))):
    yy = 176 + 36 * i
    text(BX0, yy, lab, "m")
    text(BX1, yy, f"{a:.2f}", "m", "end")
    out.append(f'<rect x="{BX0}" y="{yy + 6}" width="{bx(a) - BX0:.1f}" height="10" class="{cls}"/>')
    out.append(f'<path d="M{bx(lo):.1f} {yy + 21} H{bx(hi):.1f} M{bx(lo):.1f} {yy + 18} V{yy + 24} '
               f'M{bx(hi):.1f} {yy + 18} V{yy + 24}" class="ax"/>')
text(BX0, 322, "bar from 0.5 (chance) to 1.0; line below = 95% interval", "lbs")
text(BX0, 338, "paired with cosine, only the reranker's lead is", "lbs")
text(BX0, 352, "clearly above zero (brand-removed sits at the edge);", "lbs")
text(BX0, 366, "without the 8 bare terms: cosine 0.88, the other", "lbs")
text(BX0, 380, "three 0.95–0.96", "lbs")
out.append('<rect x="1220" y="402" width="320" height="112" rx="9" class="ex"/>')
for i, line in enumerate(("Filled dot: answerable · open dot: not.", "Labels are ours. 2D's 20 benchmark cases",
                          "plus 23 probes we wrote after seeing the", "data: a stress test, not a traffic estimate.",
                          "Scores exact: 2D's model, no LLM.")):
    text(1236, 424 + 18 * i, line, "m")
svg_gate, H_GATE = done(540)

# ================================================================ 8 · where hybrid search counts
out, P = [], "hy"
header(20, 28, "HOW THE TWO SEARCHES REACH THE DECISION")
box(160, 46, 220, 50, "a question", [], cls="nd")
box(20, 130, 240, 76, "BM25, top 4", ["text.split() tokens:", "case and punctuation kept"], cls="ep")
box(280, 130, 240, 76, "FAISS, top 4", ["all-MiniLM-L6-v2,", "nearest by cosine"], cls="ep")
fl("M220 96 V128")
fl("M330 96 V128")
box(150, 240, 240, 66, "RRF merge", ["up to 8 candidates"], cls="ep")
fl("M140 206 V222 H230 V238")
fl("M400 206 V222 H310 V238")
box(150, 336, 240, 66, "score_query", ["cosine of each candidate"], cls="ep")
fl("M270 306 V334")
box(150, 432, 240, 66, "sort by cosine", ["RRF order dropped"], cls="ep")
fl("M270 402 V430")
box(20, 532, 240, 66, "gate: top_sim", ["the best cosine"], cls="wb")
box(290, 532, 240, 66, "answer prompt", ["all candidates' text"], cls="repb")
fl("M220 498 V530")
fl("M330 498 V530")
out.append('<rect x="560" y="226" width="216" height="248" rx="9" class="nt"/>')
for i, line in enumerate(("FAISS's top 4 always holds", "the best-cosine entry, so", "top_sim is the best cosine",
                          "over all 25 entries.", "", "BM25's picks reach the", "answer prompt as extra",
                          "context, never the gate.", "", "True by construction, and", "for all 44 queries in our",
                          "retrieval check (2D's 20", "plus 24 probes).")):
    if line:
        text(574, 250 + 17 * i, line, "m")
header(800, 28, "EXACT-TERM QUESTIONS: WHAT BM25 FINDS, AND WHERE THE GATE SENDS THEM")
for x, t in zip((800, 1010, 1310, 1400), ("question", "BM25's first pick (2D's tokens)", "top_sim", "route")):
    text(x, 62, t, "t3")
ROWS8 = [("WinFsp", "manual-selective-sync ✓", 0.279), ("TOTP seed", "ticket-1175 ✓", 0.296),
         ("501(c)(3)", "faq-010 ✓", 0.275), ("MDM .msi", "manual-install ✓", 0.315),
         ("CMEK", "none: text has “(CMEK)”", 0.112), ("SCIM bearer token", "manual-admin-sso ✓", 0.394),
         ("file.shared webhook", "none: text has “file.shared,”", 0.429),
         ("cloudsync push --resumable", "ticket-1108 ✓ (manual-cli also)", 0.516)]
for i, (q, pick, s) in enumerate(ROWS8):
    yy = 92 + 34 * i
    out.append(f'<path d="M800 {yy + 12} H1540" class="gr"/>')
    text(800, yy, q, "pm")
    text(1010, yy, pick, "m")
    text(1310, yy, f"{s:.3f}", "m")
    z, cls = ("escalate", "wb") if s < 0.35 else (("judge", "nt") if s < 0.55 else ("answer", "repb"))
    out.append(f'<rect x="1400" y="{yy - 13}" width="86" height="19" rx="9.5" class="{cls}"/>')
    text(1443, yy + 1, z, "m", "middle")
for i, line in enumerate((
        "Five of these eight escalate without an LLM call, although both searches rank the right entry first for four",
        "of them: a bare term's cosine is low even when it points at the right entry. BM25 splits on whitespace only,",
        "so it is case-sensitive and keeps punctuation: 308 of the 1,569 tokens in the knowledge base begin or end",
        "with punctuation, and “CMEK”, “file.shared webhook” and “2fa” score zero on every entry (the text has",
        "“(2FA)?”). ✓ = an entry that answers it. Scores exact (our check).")):
    text(800, 466 + 20 * i, line, "s")
svg_hy, H_HY = done(620)

# ================================================================ 9 · threat model
out, P = [], "tm"
TM_BOTTOM = 800
out.append(f'<rect x="226" y="40" width="486" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(242, 62, "TB2 · the machine running the app", "tbt")
out.append(f'<rect x="790" y="40" width="224" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(806, 62, "TB3 · third-party services", "tbt")
out.append(f'<path d="M206 40 V{TM_BOTTOM + 30}" class="tbl"/>')
text(200, 56, "TB1", "tbt", "end")
text(200, 72, "browser", "lbs", "end")
person(70, 110, "Customer", "any visitor")


def tbox(x, y, w, h, title, lines, threats, cls="bx"):
    box(x, y, w, h, title, lines, cls=cls)
    badges(x, y, w, h, threats)


tbox(246, 90, 446, 110, "Streamlit app (app.py)", ["no login; trace shows candidates' full text;",
                                                   "sidebar box for an API key"], ["T8", "T6", "T4", "T3", "T1"],
     cls="ep")
store(486, 216, 206, 56, "D5", "process environment", ["OPENAI_API_KEY"])
badges(486, 216, 206, 56, ["T6"])
fl("M600 202 V214")
label(592, 212, "API key (sidebar)", "end", "lbs")
tbox(246, 288, 446, 130, "LangGraph bot and retriever", ["customer text and entries go into prompts;",
                                                         "escalation only writes a message"],
     ["T10", "T7", "T5", "T2", "T1"], cls="nd")
fl("M360 202 V286", "both")
label(368, 250, "questions, state", cls="lbs")
fl("M640 274 V286")
label(648, 284, "key", cls="lbs")
store(246, 438, 200, 96, "D1", "data/*.json", ["FAQs, ticket notes,", "manuals"])
badges(246, 438, 200, 96, ["T11", "T1"])
fl("M346 436 V420")
label(354, 432, "entries", cls="lbs")
tbox(486, 438, 206, 130, "Packages and model", ["no lock file; MiniLM", "fetched by name"], ["T9"])
fl("M589 436 V420")
label(597, 432, "code, model", cls="lbs")
tbox(806, 250, 192, 190, "OpenAI API", ["questions and candidate", "entry text; judge on", "borderline, answer on",
                                        "the answer route"], ["T8", "T7"], cls="ex")
tbox(806, 470, 192, 52, "Hugging Face Hub", [], ["T9"], cls="ex")
tbox(806, 530, 192, 52, "PyPI", [], ["T9"], cls="ex")
fl("M110 130 H244")
text(200, 122, "questions", "lbs", "end")
fl("M244 170 H110")
text(200, 186, "answers, trace", "lbs", "end")
fl("M694 330 H804", "lnr")
text(751, 323, "prompts", "lbs", "middle")
fl("M804 380 H694", "lnr")
text(751, 373, "replies", "lbs", "middle")
fl("M804 496 H694", "lnr")
text(751, 489, "weights", "lbs", "middle")
fl("M804 556 H694", "lnr")
text(751, 549, "packages", "lbs", "middle")
out.append('<rect x="260" y="604" width="420" height="34" rx="8" class="nt"/>')
text(272, 620, "Red arrows: data crossing TB3, to or from a third party", "m")
text(272, 633, "TB1 browser → app · TB2 the app's machine · TB3 outside services", "m")
THREATS = [
    ("T1", "Information disclosure · internal content", "The trace and the answers can quote agent-only ticket notes",
     "to customers (“refund the second charge…”).", "today: none"),
    ("T2", "Tampering · prompt injection", "Customer text and entry text go into both prompts; a message",
     "can try to override the rules.", "today: system prompts only"),
    ("T3", "Repudiation · no record", "Nothing is stored, so no one can show what the bot told a",
     "customer, or why.", "today: none"),
    ("T4", "Spoofing · no customer identity", "The bot can't know who is asking, so any account-specific",
     "answer or action would be unsafe.", "today: no actions exist"),
    ("T5", "Elevation of privilege · social engineering", "“Refund me” reaches the answer step with an agent note;",
     "recovery steps can be quoted to anyone.", "today: answer prompt rules only"),
    ("T6", "Elevation of privilege · shared API key", "A key typed in the sidebar sets os.environ for the whole",
     "process, so every later visitor runs on it.", "today: none"),
    ("T7", "Information disclosure · third party", "Questions, which may hold personal data, and candidate text",
     "go to OpenAI.", "today: retrieval stays local"),
    ("T8", "Denial of service · cost", "No login or rate limit; each question can make two LLM",
     "calls on the operator's key.", "today: none"),
    ("T9", "Tampering · supply chain", "No lock file and 3 packages with no upper bound; the model is",
     "fetched by name with no pinned revision.", "today: version ranges, 3 open-ended"),
    ("T10", "Failure · lost cases", "Escalated customers are told an agent will reach out; no",
     "ticket exists, so no one does.", "today: none"),
    ("T11", "Failure · stale or wrong content", "Entries have no owner, date or expiry; an outdated fix is",
     "answered as fact.", "today: none"),
]
out.append(f'<rect x="1040" y="40" width="500" height="{TM_BOTTOM - 40}" rx="12" class="nt"/>')
text(1056, 64, "Threats (STRIDE) and failures, and what the code does today", "t2")
text(1056, 82, "STRIDE: spoofing, tampering, repudiation, information disclosure,", "m")
text(1056, 96, "denial of service, elevation of privilege", "m")
for i, (tid, title, a, b, today) in enumerate(THREATS):
    yy = 124 + 62 * i
    out.append(f'<rect x="1054" y="{yy - 13}" width="34" height="18" rx="9" class="wb"/>')
    text(1071, yy, tid, "wbt", "middle")
    text(1096, yy, title, "t3")
    text(1096, yy + 15, a, "m")
    text(1096, yy + 29, b, "m")
    text(1096, yy + 43, today, "mi")
    for s_ in (a, b):
        fits(s_, 430, "m", tid)
svg_tm, H_TM = done(TM_BOTTOM + 44)

# ================================================================ 10 · the evaluation
out, P = [], "ev"
box(14, 40, 250, 130, "eval_set.py", ["20 written cases:", "18 answer, 2 escalate;", "expected entry + phrase"], cls="dt")
box(300, 40, 250, 130, "bot", ["needs an OpenAI key;", "retrieve, grade, then", "answer or escalate"], cls="ep")
box(586, 40, 300, 130, "eval.py grade()", ["pass if it escalated when expected,", "or answered with the expected",
                                           "top entry and phrase (when set)"], cls="nd")
box(922, 40, 270, 130, "“FCR” = passes ÷ 20", ["plus a failure breakdown;", "exit code 1 below 70%;",
                                                "nothing saved"], cls="nd")
fl("M264 105 H298")
fl("M550 105 H584")
fl("M886 105 H920")
out.append('<rect x="1228" y="30" width="312" height="180" rx="9" class="repb"/>')
text(1244, 52, "What decides each of the 20 (our check)", "t3")
SEG = [(15, "barK", "answer step directly (incl. Salesforce)"), (4, "barJ", "LLM judge first"),
       (1, "barU", "escalated, no LLM (dark mode)")]
xx = 1244
for n, cls, _ in SEG:
    w = n * 14
    out.append(f'<rect x="{xx}" y="66" width="{w}" height="18" class="{cls}"/>')
    xx += w
for i, (n, cls, lab) in enumerate(SEG):
    out.append(f'<rect x="1244" y="{98 + 20 * i}" width="12" height="12" class="{cls}"/>')
    text(1262, 108 + 20 * i, f"{n} · {lab}", "m")
text(1244, 174, "Top entry correct in 18 of 18 answer cases:", "m")
text(1244, 190, "a wrong-document failure can't happen here.", "m")
out.append('<rect x="14" y="236" width="760" height="256" rx="9" class="nt"/>')
text(30, 260, "2D's “FCR” and FCR in a support team", "t3")
for x, t in ((30, ""), (190, "2D's benchmark"), (470, "a support team's FCR")):
    text(x, 286, t, "t3")
CMP = [("unit", "a written question", "a customer's issue"),
       ("a correct escalation", "counts as resolved", "counts only if an agent solves it"),
       ("", "", "in the same contact"),
       ("questions from", "18 restated or paraphrased", "a sample of real traffic"),
       ("", "entries, 2 out of scope", ""),
       ("measured", "offline, one run", "in production, with a reopen window"),
       ("reported with", "pass/fail per case; counts of false", "reopen rate, repeat contacts,"),
       ("", "answers, false escalations, wrong", "satisfaction (CSAT)"),
       ("", "entry, missing phrase (printed)", "")]
for i, (a, b, c) in enumerate(CMP):
    yy = 310 + 21 * i
    text(30, yy, a, "s")
    text(190, yy, b, "s")
    text(470, yy, c, "s")
box(794, 236, 746, 256, "What a fair version adds", [
    "a few hundred real tickets labelled answerable or not, with the right outcome; a third held out",
    "request rules first: account actions, exceptions, legal threats, complaints, “talk to a human” and",
    "two failed tries go to a person; how-to questions on the same topics go through the gate",
    "a confidence score shortlisted by AUC, then chosen at the agreed wrong-answer rate",
    "offline: answer precision, wrong-answer rate, escalation rate and judge accuracy per intent",
    "then shadow mode, agent assist and a small random share of live traffic, measuring real FCR,",
    "the bot's resolution rate, containment, repeat contacts, satisfaction and cost per resolved issue",
    "every run stored, with the route and outcome of each question"], cls="nt", step=24)
svg_ev, H_EV = done(512)

# ================================================================ 11 · the recommended architecture
out, P = [], "rc"
header(20, 28, "WHAT AN FDE WOULD BUILD · the number in a corner is the 2.5 decision that part answers")
box(560, 40, 320, 92, "Content pipeline", ["help-centre sync: versions, owner, expiry;",
                                          "ticket notes rewritten or kept agent-only;",
                                          "personal data scrubbed"], cls="nd", tag="1, 14")
person(60, 190, "Customer", "via the widget")
box(110, 175, 160, 116, "Chat widget", ["in the help desk;", "passes the", "customer's identity;", "says it is an AI"],
    cls="nd", tag="13")
fl("M86 221 H108", "both")
out.append('<rect x="320" y="150" width="860" height="250" rx="14" class="bndc"/>')
text(336, 172, "SUPPORT BOT SERVICE", "h")
text(1166, 172, "approved LLM vendor and region · every request logged, redacted", "lbs", "end")
fl("M272 234 H318", "both")
label(295, 216, "question", "middle")
label(295, 252, "reply", "middle")
fl("M640 132 V188")
label(648, 145, "approved, versioned entries")
box(340, 190, 190, 116, "Request rules", ["account actions,", "exceptions, legal", "threats, complaints,",
                                          "“a human”, 2 failures"], cls="nd", tag="10")
box(550, 190, 190, 116, "Hybrid retrieval", ["BM25 with normalized", "tokens + embeddings", "over approved content",
                                             "(multilingual if needed)"], cls="nd", tag="3, 4")
box(760, 190, 190, 116, "Confidence gate", ["score picked by AUC", "(a reranker leads);", "cut-offs from the error",
                                            "budget; middle: clarify"], cls="nd", tag="5, 6, 7")
box(970, 190, 190, 116, "Answer", ["cites [id], checked", "against the context;", "no promised refunds",
                                   "or access changes"], cls="nd", tag="8")
for x in (532, 742, 952):
    fl(f"M{x} 240 H{x + 16}")
box(340, 330, 820, 58, "Escalate", ["create the help-desk ticket with transcript, candidates and reason; tell the "
                                    "customer the real next step"], cls="nd", tag="9")
fl("M430 308 V328")
label(438, 322, "rule match")
fl("M820 308 V328")
label(828, 322, "low score")
fl("M1060 308 V328")
label(1068, 322, "not supported")
box(760, 440, 260, 76, "Help-desk ticketing", ["queues by reason; service levels"], cls="ex")
fl("M890 390 V438")
label(898, 424, "ticket")
person(1100, 444, "Support agent", "by queue")
fl("M1022 478 H1074")
box(340, 440, 360, 108, "Logs and metrics", ["every request: route and outcome, redacted;",
                                             "FCR, bot resolution rate, containment,",
                                             "repeat contacts, CSAT, cost per resolved issue;",
                                             "content gaps to knowledge managers"], cls="dt", tag="11, 12")
fl("M480 402 V438")
label(488, 424, "every request")
box(1230, 190, 310, 90, "LLM vendor", ["approved vendor and region;", "answer step, and the judge if kept"], cls="ex")
fl("M1182 235 H1228", "both")
label(1205, 228, "calls", "middle")
text(20, 586, "ROLLOUT, IN STAGES", "rl")
STAGES = [("1 · Data-access approval", ["vendor, region, redaction", "(2.8 step 3)"], None),
          ("2 · Offline evaluation", ["labelled real tickets; score", "by AUC, cut-offs at budget"], "5, 6, 12"),
          ("3 · Shadow mode", ["answers silently, graded", "against what agents did"], None),
          ("4 · Agent assist", ["agents accept, edit or", "reject the drafts"], None),
          ("5 · Customer-facing sign-off", ["AI disclosure, injection", "tests (2.8 step 10)"], None),
          ("6 · Small random share", ["real FCR, resolution rate,", "CSAT, cost per resolved issue"], None)]
for i, (t, ls, tg) in enumerate(STAGES):
    x = 20 + i * 256
    box(x, 598, 240, 82, t, ls, cls="nt", tag=tg)
    if i:
        fl(f"M{x - 16} 639 H{x - 2}")
svg_rc, H_RC = done(700)

# ================================================================ page
FIGS = [
    ("context", "System context", "Before anything else: what the system is, who uses it, and what it depends on.",
     svg_ctx, 1560, H_CTX,
     "System context: a customer or tester asks the support bot questions; the bot reads 25 hand-written entries, "
     "calls the OpenAI API for the judge and the answer, downloads its embedding model from the Hugging Face Hub, "
     "and installs packages from PyPI; no flow reaches a support agent."),
    ("architecture", "High-level architecture", "Then the parts and where they run: one process, four steps.",
     svg_ar, 1560, H_AR,
     "High-level architecture: inside one Python process, app.py or eval.py, used by a customer or tester, calls a "
     "LangGraph workflow with retrieve, "
     "grade, answer and escalate steps; the retriever combines BM25 and FAISS over the knowledge base; OpenAI serves "
     "the judge and the answer, and the Hugging Face Hub the embedding model."),
    ("kb", "The knowledge base and the benchmark", "Then what the bot knows, and what the 20 questions test.",
     svg_kb, 1560, H_KB,
     "The knowledge base and the benchmark: 25 entries by source, 16 of them tested by the benchmark; examples of "
     "agent-facing and version-specific ticket notes; the 20 benchmark cases by type, what a case must show to pass, "
     "and what the benchmark leaves out."),
    ("dataflow", "Data flow (level 1)", "Then what data moves between the parts, and where it is stored.",
     svg_dfd, 1560, H_DFD,
     "Level-1 data flow: entries and model weights build the BM25 and FAISS indexes; each question is retrieved, "
     "scored, graded, then answered or escalated, with the judge and answer prompts sent to OpenAI; the answer and the "
     "full trace return to the customer; no flow reaches a support agent."),
    ("design", "Detailed design", "Then each file's key functions and settings, with what is broken.",
     svg_design, 1560, H_DESIGN,
     "Detailed design: the repository's files with their key functions and settings, and twelve numbered review "
     "notes, from the gate score that BM25 never reaches to the unpinned model."),
    ("sequence", "Sequence: one question, three routes", "Then one question through the workflow, call by call.",
     svg_seq, 1560, H_SEQ,
     "Sequence of one question: hybrid retrieval, cosine scoring and a sort; then one of three routes by top_sim, with "
     "an LLM judge call only in the middle band; on the answer route an LLM call writes the reply or flags "
     "INSUFFICIENT_CONTEXT; escalation sends nothing to anyone."),
    ("gate", "What the confidence gate sees", "Then whether the gate's score can tell the two kinds of question apart.",
     svg_gate, 1560, H_GATE,
     "What the confidence gate sees: 43 queries plotted by top_sim against the 0.35 and 0.55 cut-offs, 30 answerable "
     "and 13 not; the two groups overlap, the product name moves questions across the bands, and four candidate "
     "scores are compared by AUC, from 0.76 for 2D's cosine to 0.94 for a cross-encoder reranker."),
    ("hybrid", "Where hybrid search counts", "Then what BM25 changes in the pipeline, and what it doesn't.",
     svg_hy, 1560, H_HY,
     "Where hybrid search counts: BM25 and FAISS candidates are merged and re-sorted by cosine, so the gate always "
     "sees the best FAISS match and BM25 only adds context; a table of eight exact-term questions, what BM25 finds "
     "for each, and where the cosine score sends them."),
    ("threats", "Threat model", "With all of that drawn: where it can be attacked or fail, and what protects it today.",
     svg_tm, 1560, H_TM,
     "Threat model: trust boundaries between the customer's browser, the app's machine and third-party services; "
     "nine STRIDE threats and two failures, from internal ticket notes shown to customers to stale content, each "
     "marked on the part it affects."),
    ("evaluation", "The evaluation", "Then what 2D's “FCR” measures, and what real FCR needs.",
     svg_ev, 1560, H_EV,
     "The evaluation: 20 written cases run through the bot and graded on routing, expected entry and phrase; what "
     "decides each case; 2D's FCR compared with a support team's FCR; and what a fair version adds."),
    ("recommended", "The recommended architecture", "Finally: the design an FDE would build, with the 2.5 decision each numbered part answers.",
     svg_rc, 1560, H_RC,
     "The recommended architecture: a chat widget in the help desk that passes the customer's identity; a support bot service that applies request rules, hybrid retrieval over approved content, a confidence gate and a cited answer, and escalates into real help-desk tickets; content, logging and metrics pipelines; and a staged rollout from data-access approval and offline evaluation through shadow mode to a small share of live traffic."),
]
FDE = Path(__file__).with_name("fde_2d.html").read_text(encoding="utf-8")
for tok in ("gpt-4o-mini", "all-MiniLM-L6-v2", "INSUFFICIENT_CONTEXT", "first-contact", "cross-encoder",
            "agent-assist", "e-commerce"):
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
           ("fde-stress", "2.7", "Checking the gate"), ("fde-plan", "2.8", "Engagement steps"),
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
    itself, behaviour, what the gate sees, where hybrid search counts, risk and the evidence, then the design an FDE would build instead. Each answers a group
    of the questions above (see 2.9).</p>
</section>"""
PFX = {"context": "cx", "architecture": "ar", "kb": "kb", "dataflow": "df", "design": "ds", "sequence": "sq",
       "gate": "gt", "hybrid": "hy", "threats": "tm", "evaluation": "ev", "recommended": "rc"}
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
  svg .dA { fill: var(--accent); }
  svg .dU { fill: var(--surface); stroke: var(--bad); stroke-width: 2; }
  svg .bE { fill: var(--bad-soft); fill-opacity: .7; }
  svg .bJ { fill: var(--warn-soft); }
  svg .bA { fill: var(--good-soft); }
  svg .ax { fill: none; stroke: currentColor; stroke-opacity: .45; stroke-width: 1; }
  svg .gr { fill: none; stroke: currentColor; stroke-opacity: .12; stroke-width: 1; }
  svg .barA { fill: var(--accent); }
  svg .barU { fill: var(--bad); }
  svg .barJ { fill: var(--warn); }
  svg .barG { fill: var(--muted); }
  svg .barK { fill: var(--good); }
  svg .vio { fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.2; }
  svg .eeX { fill: var(--surface); stroke: currentColor; stroke-opacity: .6; stroke-width: 1.6; stroke-dasharray: 6 4; }
"""
page = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>2D: Brief to Architecture</title>\n<style>\n" + CSS + "\n</style>\n</head>\n<body>\n<header>\n"
        "  <p class=\"eyebrow\">Requirement → FDE analysis → architecture · The Gen Academy · Week 2, project 2D</p>\n"
        "  <h1>Customer Support Knowledge Base with Hybrid Search</h1>\n"
        "  <p class=\"src\">Drawn from the code at commit <a href=\"https://github.com/The-Gen-Academy/"
        "2D-Customer-Support-KB-with-Hybrid-Search/tree/6a40fa1\">6a40fa1</a> and the "
        "<a href=\"https://docs.google.com/document/d/1cGdfIbUoVpoHjrbxjcuMV8Ga59NJuvNA/edit\">solution kit</a>.</p>\n"
        "</header>\n" + nav + "\n" + body + "\n</body>\n</html>\n")
OUT.write_text(page, encoding="utf-8")
print("written:", OUT, len(FIGS), "figures")
for w in warnings:
    print("WARN", w)
