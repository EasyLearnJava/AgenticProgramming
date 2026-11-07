"""Writes the requirement, FDE analysis and architecture page of The Gen Academy's 2B Financial Document
Intelligence Pipeline as one self-contained HTML file. Reads Parts 1 and 2 from fde_2b.html beside it.
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


# ================================================================ 1 · system context
out, P = [], "cx"
out.append('<rect x="470" y="28" width="700" height="426" rx="14" class="bnd"/>')
text(1158, 48, "system boundary: the notebook and its own Pinecone index (hosted by Pinecone)", "lbs", "end")
box(600, 58, 260, 92, "Pinecone index", ["'financial-rag' · 768-d · cosine", "fixed 12,142 · semantic 2,529",
                                         "serverless, AWS us-east-1"], cls="pc")
box(520, 190, 380, 165, "Financial RAG notebook", [
    "59 cells, run on Google Colab", "downloads and cleans two Apple 10-Ks",
    "chunks them two ways, embeds, uploads", "answers questions; scores set-ups A, B, C",
    "LangChain · FlashRank · RAGAS · gpt-4o-mini"], cls="nd")
fl("M680 190 V152")
label(672, 176, "upsert 14,671 vectors · search", "end")
fl("M780 152 V190")
label(788, 176, "matching chunks")
person(160, 180, "Notebook user", "student or analyst")
fl("M196 225 H518")
label(357, 217, "runs the cells, edits the questions", "middle")
fl("M518 300 H196")
label(357, 292, "answers and the A/B/C score table", "middle")
box(1240, 40, 300, 90, "SEC EDGAR", ["public filings, no API key", "asks for a contact in the User-Agent"], cls="ex")
box(1240, 150, 300, 90, "Hugging Face Hub", ["bge-base-en-v1.5 weights, 438 MB",
                                             "FlashRank model zip, 21.6 MiB"], cls="ex")
box(1240, 255, 300, 90, "OpenAI API", ["gpt-4o-mini: answers and RAGAS judging",
                                       "text-embedding-3-small: created, unused"], cls="ex")
box(1240, 365, 300, 80, "PyPI", ["15 packages, no versions pinned"], cls="ex")
fl("M1240 85 H1190 V210 H902")
label(1040, 203, "2 full submissions, ~9.5 MB each", "middle")
fl("M1240 195 H1205 V242 H902")
label(1040, 235, "model weights, on first use", "middle")
fl("M902 280 H1238")
label(1040, 273, "prompts with chunks", "middle")
fl("M1238 312 H902")
label(1040, 305, "answers, judge verdicts", "middle")
fl("M1240 405 H1205 V342 H902")
label(1040, 335, "packages, on every new runtime", "middle")
box(560, 486, 300, 76, "Google Colab", ["the runtime: T4 GPU, disk, Python", "Colab Secrets: 3 API keys"],
    cls="ex")
fl("M710 486 V357")
label(718, 432, "GPU, disk, keys")
svg_ctx, H_CTX = done(580)

# ================================================================ 2 · high-level architecture
out, P = [], "ar"
out.append('<rect x="250" y="40" width="960" height="550" rx="14" class="bndc"/>')
text(270, 66, "GOOGLE COLAB RUNTIME · a Google cloud VM with a T4 GPU · one notebook, 59 cells", "h")
box(270, 110, 190, 110, "Download", ["sec-edgar-downloader", "AAPL 10-K, latest 2", "full submissions"],
    tag="cells 17–19", cls="ep")
box(490, 110, 210, 110, "Load and clean", ["TextLoader, 1 doc per file", "unescape; regex: tags, ix:",
                                             "→ 5.5 M chars (our check)"], tag="cells 21–23", cls="ep")
box(730, 96, 210, 66, "Fixed-size → 12,142", ["512 / 64, then filter"], cls="ep")
box(730, 172, 210, 66, "Semantic → 2,529", ["65th pct, filter, split"], cls="ep")
box(970, 110, 220, 110, "Embed and upload", ["bge-base on the T4", "batches of 100", "delete_all first"],
    tag="cells 27–33", cls="ep")
fl("M460 165 H488")
fl("M700 150 H715 V129 H728")
fl("M700 180 H715 V205 H728")
fl("M940 129 H955 V150 H968")
fl("M940 205 H955 V180 H968")
box(270, 330, 190, 100, "Retrieve", ["embed the question", "top 3, or top 10 for C"], tag="cells 43–45", cls="nd")
box(490, 330, 210, 100, "Rerank (C only)", ["FlashRank: 10 pairs → best 3", "A and B skip it: their", "top 3 go straight on"],
    tag="cell 43", cls="nd")
box(730, 330, 210, 100, "Generate", ["one prompt, 3 chunks", "gpt-4o-mini, temp. 0"], tag="cell 49", cls="nd")
box(970, 330, 220, 100, "Evaluate", ["RAGAS: 3 metrics", "10 questions × A, B, C"], tag="cells 53–59", cls="nd")
fl("M460 380 H488")
fl("M700 380 H728")
fl("M940 380 H968")
box(270, 476, 430, 64, "Local model · bge-base-en-v1.5",
    ["PyTorch on the T4: semantic chunking, upload, queries"], cls="cf")
box(730, 476, 210, 64, "Local model · FlashRank", ["ONNX Runtime, CPU"], cls="cf")
box(970, 476, 220, 64, "Colab Secrets", ["3 API keys → env variables"], cls="cf")
box(1260, 100, 280, 130, "Pinecone", ["index 'financial-rag'", "namespace 'fixed': 12,142",
                                       "namespace 'semantic': 2,529", "serverless, AWS us-east-1"], cls="pc")
box(1260, 300, 280, 110, "OpenAI API", ["gpt-4o-mini: answers", "gpt-4o-mini: RAGAS judge",
                                        "embedding model: created, unused"], cls="ex")
fl("M1190 165 H1258")
label(1214, 157, "upsert")
fl("M1258 215 H1230 V285 H365 V328", "both")
label(800, 279, "question vector → top 3 or top 10 chunks, with their text", "middle")
fl("M835 330 V306 H1244 V330 H1258", "both")
label(1040, 321, "prompt with 3 chunks ↔ answer", "middle")
fl("M1190 385 H1258", "both")
label(1214, 377, "judge")
box(20, 120, 180, 90, "SEC EDGAR", ["public 10-K filings", "no API key"], cls="ex")
fl("M200 165 H268")
label(225, 157, "2 files", "middle")
person(115, 300, "Notebook user", "in a browser")
fl("M150 362 H268")
label(209, 354, "question", "middle")
fl("M1080 430 V452 H115 V402")
out.append('<path d="M835 430 V452" class="ln"/>')
label(640, 446, "answers (cell 51) and the A/B/C score table (cell 59)", "middle")
box(20, 470, 180, 76, "Hugging Face Hub", ["model weights", "on first use"], cls="ex")
fl("M200 508 H268")
fl("M120 546 V568 H835 V542")
label(480, 562, "FlashRank model zip", "middle")
svg_ar, H_AR = done(610)

# ================================================================ 3 · data flow (level 1, Gane-Sarson)
out, P = [], "df"
ent(20, 86, 170, 60, "E1", "SEC EDGAR", "public filings")
proc(270, 70, 170, 92, "P1", "Download", ["sec-edgar-downloader", "AAPL 10-K, limit=2"])
proc(480, 70, 170, 92, "P2", "Load and clean", ["load, unescape, regex", "→ 5.5 M chars (our check)"])
proc(720, 18, 170, 92, "P3", "Chunk, fixed-size", ["512 / 64, then filter", "14,119 → 12,142"])
proc(720, 130, 170, 92, "P4", "Chunk, semantic", ["65th pct · filter · split", "3,080 → 2,529"])
proc(980, 70, 170, 92, "P5", "Embed and upload", ["bge-base on the T4", "batches of 100"])
store(270, 230, 380, 50, "D1", "sec-edgar-filings/ (Colab disk)", ["2 × full-submission.txt, ~9.5 MB each"])
store(1230, 30, 310, 50, "D2", "Pinecone · namespace 'fixed'", ["12,142 vectors + chunk text"])
store(1230, 150, 310, 50, "D3", "Pinecone · namespace 'semantic'", ["2,529 vectors + chunk text"])
fl("M190 116 H268")
label(229, 108, "2 filings", "middle")
fl("M355 162 V228")
label(363, 200, "full-submission.txt × 2")
fl("M565 228 V164")
label(573, 200, "raw text")
fl("M650 100 H685 V64 H718")
fl("M650 130 H685 V176 H718")
label(686, 122, "cleaned text", "middle", "lbs")
fl("M890 64 H930 V100 H978")
label(897, 58, "12,142 chunks", cls="lbs")
fl("M890 176 H930 V135 H978")
label(897, 194, "2,529 chunks", cls="lbs")
fl("M1150 95 H1190 V55 H1228")
fl("M1150 135 H1190 V175 H1228")
label(1190, 119, "vectors + text", "middle", "lbs")
ent(600, 300, 190, 50, "E2", "Hugging Face Hub")
fl("M790 325 H1065 V164")
label(925, 318, "bge weights (cell 15)", "middle")
fl("M760 300 V224")
label(768, 262, "bge weights (cell 15)", cls="lbs")
fl("M790 342 H1000 V418")
label(1008, 382, "bge weights (cell 15)", cls="lbs")
fl("M695 350 V418")
label(703, 392, "FlashRank weights (cell 41)")
proc(950, 420, 190, 92, "P6", "Retrieve", ["embeds the question (bge)", "A fixed, B semantic: 3", "C semantic: top 10"])
proc(600, 420, 190, 92, "P7", "Rerank", ["FlashRank, set-up C", "10 pairs → best 3"])
proc(250, 420, 190, 92, "P8", "Generate", ["one prompt + 3 chunks", "gpt-4o-mini"])
ent(20, 436, 180, 60, "E3", "Notebook user", "in a browser")
fl("M1300 200 V448 H1142")
label(1310, 330, "semantic chunks (B, C)")
fl("M1540 55 H1552 V470 H1142")
label(1544, 300, "fixed chunks (A)", "end")
fl("M948 466 H792")
label(870, 458, "10 chunks (C)", "middle", "lbs")
fl("M598 466 H442")
label(520, 458, "best 3 (C)", "middle", "lbs")
fl("M1045 512 V545 H420 V514")
label(700, 539, "3 chunks (A, B: no rerank)", "middle", "lbs")
fl("M248 466 H202")
label(225, 458, "answer", "middle", "lbs")
ent(250, 600, 390, 50, "E4", "OpenAI API", "gpt-4o-mini: answers and judge verdicts")
fl("M270 512 V598")
label(264, 562, "prompt +", "end", "lbs")
label(264, 576, "3 chunks", "end", "lbs")
fl("M310 598 V514")
label(316, 572, "answer", cls="lbs")
proc(720, 586, 190, 92, "P9", "Evaluate", ["RAGAS, 3 metrics", "per question, A/B/C"])
fl("M360 512 V560 H760 V584")
label(560, 574, "answer + 3 chunks, per question and set-up", "middle", "lbs")
fl("M720 612 H642")
label(681, 606, "judge calls", "middle", "lbs")
fl("M642 640 H718")
label(681, 634, "verdicts", "middle", "lbs")
store(700, 720, 340, 50, "D4", "eval_dataset (in memory)", ["10 questions + reference answers"])
fl("M800 720 V680")
label(808, 704, "references", cls="lbs")
fl("M1040 745 H1120 V514")
label(1128, 640, "evaluation questions (cell 55)", cls="lbs")
fl("M720 665 H160 V498")
label(440, 680, "the A/B/C score table", "middle", "lbs")
proc(420, 690, 200, 70, "P10", "Write the eval set", ["cell 53"])
fl("M140 496 V721 H418")
label(280, 715, "10 questions + references", "middle", "lbs")
fl("M620 745 H698")
fl("M110 496 V800 H1520 V500 H1142")
label(800, 794, "a question (cells 47–51)", "middle", "lbs")
svg_dfd, H_DFD = done(820)

# ================================================================ 4 · data model
out, P = [], "dm"
C1, C2, C3, CW = 20, 540, 1060, 480
y = 20
y += card(C1, y, CW, "EDGAR full submission · a file", [
    ("path", "sec-edgar-filings/AAPL/10-K/<accession>/"), ("", "full-submission.txt"),
    ("size", "about 9.5 MB each, 2 files"), ("holds", "the 10-K + ~70 XBRL viewer pages, the XBRL instance,"),
    ("", "JSON, linkbases, exhibits, uuencoded ZIP and images")], 70, sub="downloaded by cell 17", cls="dt") + 20
y += card(C1, y, CW, "Document · LangChain", [("page_content", "cleaned text, 2.7–2.8 M characters (our check)"),
                                              ("metadata.source", "the file path")], 130,
          sub="TextLoader (cell 21), then cell 23's cleaning") + 20
y += card(C1, y, CW, "Chunk · a Document", [("page_content", "fixed: ≤ 512 characters, average 431"),
                                            ("", "semantic: ~2,000 avg (2,246 pre-split), ≤ 8,000"),
                                            ("metadata.source", "copied from the Document")], 130,
          sub="cells 25, 31 and 33") + 20
y1 = y
y = 20
y += card(C2, y, CW, "Pinecone record", [("id", "a random UUID (uuid4)"),
                                         ("values", "768 floats, bge-base, normalized"),
                                         ("metadata.text", "the chunk text"), ("metadata.source", "the file path"),
                                         ("namespace", "'fixed' or 'semantic'")], 130,
          sub="index 'financial-rag' · cosine · langchain-pinecone", cls="pc") + 20
y += card(C2, y, CW, "Retrieved chunk · a Document", [("page_content", "read back from metadata.text"),
                                                      ("metadata.source", "the file path"),
                                                      ("metadata.rerank_score", "set in place, set-up C only")],
          170) + 20
y += card(C2, y, CW, "FlashRank RerankRequest", [("query", "the question"),
                                                 ("passages", "a list of 10 {id: 0–9, text}")], 80) + 20
y += card(C2, y, CW, "FlashRank result · a list", [("each item", "id, text, score"),
                                                   ("order", "best score first; the top 3 are kept")], 80) + 20
y2 = y
y = 20
y += card(C3, y, CW, "rag_answer() result", [("answer", "a string, from StrOutputParser"),
                                             ("sources", "the 3 Documents used")], 80, cls="nd") + 20
y += card(C3, y, CW, "eval_dataset item · 10 of them", [("question", "8 reported figures, 2 narrative"),
                                                        ("ground_truth", "a reference answer, no source")], 110,
          cls="dt") + 20
y += card(C3, y, CW, "results row · 3 lists × 10 rows", [("question", "from eval_dataset"),
                                                         ("answer", "gpt-4o-mini's answer"),
                                                         ("contexts", "the 3 chunk texts"),
                                                         ("ground_truth", "the reference answer")], 110) + 20
y += card(C3, y, CW, "RAGAS scores → comparison table", [("per row", "faithfulness, context_precision,"),
                                                         ("", "context_recall, each 0–1"),
                                                         ("extract_score", "the mean, ignoring NaN"),
                                                         ("DataFrame", "Metric × A, B, C (cell 59)")], 110) + 20
y3 = y
yb = max(y1, y2, y3)
hs = card(C1, yb, CW, "Settings · spread across cells", [
    ("index", "'financial-rag' · 768 · cosine · aws us-east-1"), ("fixed", "chunk_size 512, overlap 64"),
    ("semantic", "percentile 65 · MAX_CHARS 8,000, overlap 100"), ("upload", "BATCH_SIZE 100"),
    ("retrieval", "k 3 (A, B) · k 10 → top_n 3 (C)"),
    ("models", "bge-base-en-v1.5 · MiniLM-L-12-v2 · gpt-4o-mini")], 80, cls="cf")
out.append(f'<rect x="{C2}" y="{yb}" width="{C3 + CW - C2}" height="{hs}" rx="9" class="nt"/>')
text(C2 + 12, yb + 22, "How the structures turn into each other", "t2")
for i, line in enumerate((
        "file → Document: TextLoader; metadata.source = the path; cleaned in place by cell 23",
        "Document → chunks: the splitter or SemanticChunker; metadata is copied to every chunk",
        "chunk → Pinecone record: embedded by bge; text and source go into metadata; the id is random",
        "record → retrieved Document: similarity_search turns metadata.text back into page_content",
        "results rows → Dataset.from_list → RAGAS evaluate → per-row scores → means → DataFrame",
        "no metadata field holds the fiscal year, section or page; the form and accession sit only in the path "
        "(and in any page footer inside the text)")):
    text(C2 + 12, yb + 46 + 17 * i, line, "m")
    fits(line, C3 + CW - C2 - 24, "m", "mapping")
svg_dm, H_DM = done(yb + hs + 20)

# ================================================================ 5 · detailed design: the notebook
out, P = [], "ds"
SECTIONS = [
    ("1 · Setup · cells 2–15", ["pip install 15 packages, no versions (cell 4) · checks the T4 GPU",
                                "Colab Secrets → 3 env variables · a test call to gpt-4o-mini",
                                "create or reuse index 'financial-rag' (768, cosine, aws us-east-1)",
                                "load bge-base-en-v1.5 on cuda, normalize_embeddings=True"], [9, 8]),
    ("2 · Ingestion · cells 17–21", ["Downloader('LearningProject', 'test@example.com')",
                                     ".get('10-K', 'AAPL', limit=2) → 2 × full-submission.txt",
                                     "TextLoader(utf-8, autodetect) · metadata['source'] = path"], [3, 2]),
    ("3 · Preprocessing · cell 23", ["clean_edgar_text: unescape entities, drop tags and ix: fragments,",
                                     "blank symbol-only lines, collapse blank lines and runs of spaces",
                                     "then remove_edgar_header(text): never defined · re: never imported"], [1]),
    ("4A · Fixed-size · cells 25–29", ["RecursiveCharacterTextSplitter(512, 64, separators \\n\\n, \\n, '. ', ' ', '')",
                                       "is_clean_chunk: drop < 100 chars or < 40% letters · 14,119 → 12,142",
                                       "delete_all('fixed') · from_documents + add_documents, 100 at a time"], [4]),
    ("4B · Semantic · cells 31–33", ["SemanticChunker(embeddings, 'percentile', 65) · filter: 3,080 → 2,245",
                                     "split chunks over 8,000 characters (overlap 100) → 2,529",
                                     "delete_all('semantic') · upload 100 at a time"], [6, 5]),
    ("5 · Retrieval testing · cells 35–39", ["connect to both namespaces · 5 test queries · top 1 of 3, side by side"],
     [10]),
    ("6 · Reranking · cells 41–47", ["Ranker('ms-marco-MiniLM-L-12-v2'), max_length 512 by default",
                                     "retrieve_no_rerank(k=10) · retrieve_with_rerank(k=10, top_n=3)",
                                     "retrieve_fixed(k=3)"], [7, 6]),
    ("7 · Generation · cells 49–51", ["ChatPromptTemplate.from_template: one user message · temperature 0",
                                      "format_context joins chunks with '---'",
                                      "rag_answer(query, use_reranker=True, k=10, top_n=3)"], []),
    ("8 · RAGAS · cells 53–57", ["10 questions + ground truths · A, B and C answered in one loop (cell 55)",
                                 "evaluate(Dataset.from_list(rows), [faithfulness, context_precision,",
                                 "context_recall]) · judge gpt-4o-mini (RAGAS sets temperature 0.01)"], [10]),
    ("9 · Results · cell 59", ["extract_score: the mean, ignoring NaN · comparison DataFrame · winner"], []),
]
y = 20
for title, lines, notes in SECTIONS:
    h = 34 + 16 * len(lines) + 8
    box(20, y, 760, h, title, lines, cls="ep" if title[0] in "1239" else "nd", warn=notes)
    y += h + 12
H_DESIGN_LEFT = y
NOTES = [
    ("Cell 23 calls remove_edgar_header and re.sub, but no cell defines the function or imports re.",
     "On a fresh runtime the notebook stops here, though the README says “Run all cells top to bottom”."),
    ("limit=2 means the latest two 10-Ks at run time: FY2024 and FY2025 in the saved outputs (cell 19).",
     "After Apple's next filing the same cell fetches FY2025 and FY2026; nothing pins the filings used."),
    ("full-submission.txt is the whole EDGAR package. About 9% of the fixed-size chunks are 10-K text;",
     "the rest is XBRL (viewer pages, instance), JSON, linkbases, exhibits and uuencoded binary (our check)."),
    ("The filter keeps the answers: for every numeric evaluation question, kept chunks hold the figure with",
     "its row label (19 hold “Total net sales” and “391,035”). It drops 11 of 13 for Americas (our check)."),
    ("Tables survive semantic chunking because the sentence splitter only breaks where “.”, “?” or “!”",
     "meets whitespace, which a flattened table rarely contains (langchain-experimental source)."),
    ("bge-base (max_seq_length 512) and FlashRank (max_length 512, question included) read 512 tokens at most:",
     "≈ the first 2,000 characters of prose; long chunks are embedded and scored on their opening only."),
    ("A markdown cell says “Retrieve top-20 candidates”; the code retrieves 10.", ""),
    ("HuggingFaceEmbeddings adds no query instruction (langchain-huggingface source), though the",
     "solution kit says LangChain adds BGE's prefix automatically."),
    ("No package versions are pinned. HUGGINGFACEHUB_API_TOKEN is not the variable the Hub reads,",
     "so model downloads run unauthenticated (cell 15's warning)."),
    ("Four evaluation questions (one reworded) were also used in cells 37–51 to inspect retrieval while",
     "building; the ingestion cells (17–33) keep outputs from an earlier session."),
]
out.append(f'<rect x="810" y="20" width="730" height="{H_DESIGN_LEFT - 32}" rx="9" class="nt"/>')
text(826, 44, "Review notes · numbered on the cells they affect", "t2")
for i, (a, b) in enumerate(NOTES):
    yy = 76 + i * 88
    dot(838, yy - 4, i + 1)
    text(858, yy, a, "m")
    fits(a, 670, "m", f"note {i + 1}")
    if b:
        text(858, yy + 16, b, "m")
        fits(b, 670, "m", f"note {i + 1}")
svg_design, H_DESIGN = done(H_DESIGN_LEFT + 8)

# ================================================================ 6 · the two chunking paths
out, P = [], "ch"
header(20, 28, "WHERE THE FIXED-SIZE CHUNKS COME FROM · our check: each part of the 2 submissions chunked separately")
PARTS = [("10-K text", 1096, "pc"), ("XBRL XML: viewer pages, instance", 4646, "nt"), ("JSON metadata", 4240, "nt"),
         ("uuencoded binary", 1156, "nt"), ("exhibits", 719, "nt"), ("linkbases", 381, "nt")]
total, x = sum(n for _, n, _ in PARTS), 20.0
for name, n, cls in PARTS:
    w = 1520 * n / total
    out.append(f'<rect x="{x:.1f}" y="46" width="{w:.1f}" height="38" class="{cls}"/>')
    pct = f"{100 * n / total:.0f}%"
    s = f"{name} {pct}" if w > 9 * len(name) + 30 else pct
    text(x + w / 2, 70, s, "t3", "middle")
    if s == pct:
        text(x + w / 2, 102, name, "lbs", "middle")
    x += w
text(20, 120, "12,238 chunks in this estimate; the notebook chunks the whole cleaned text (5.52 M characters by our "
              "check; the docs say ~7.6 M) into 12,142", "lbs")
header(20, 158, "A · FIXED-SIZE")
header(820, 158, "B AND C · SEMANTIC")
box(40, 172, 680, 64, "RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)",
    ["cuts at a blank line, a line break, '. ' or a space, whichever keeps chunks under 512"])
fl("M380 236 V370")
label(390, 306, "14,119 chunks")
box(40, 372, 680, 64, "is_clean_chunk filter", ["drops chunks under 100 characters or under 40% letters"])
fl("M380 436 V470")
label(390, 458, "12,142 kept · average 431 characters")
box(40, 472, 680, 64, "embed with bge-base → namespace 'fixed'", ["12,142 vectors, each with its text"], cls="pc")
box(820, 172, 700, 64, "split into sentences", ["breaks only where '.', '?' or '!' meets whitespace: a flattened table stays one “sentence”"])
fl("M1170 236 V270")
box(820, 272, 700, 64, "embed each sentence with its neighbours (bge on the T4)",
    ["cut where the distance between neighbours is above its 65th percentile"])
fl("M1170 336 V370")
label(1180, 358, "3,080 chunks")
box(820, 372, 700, 64, "same filter, then split chunks over 8,000 characters",
    ["2,245 kept (average 2,246) → 2,529 after the split, about 2,000 each"])
fl("M1170 436 V470")
box(820, 472, 700, 64, "embed with bge-base → namespace 'semantic'", ["2,529 vectors, each with its text"],
    cls="pc")
header(20, 586, "WHAT TOP 3 HANDS THE MODEL · three average chunks")
out.append('<rect x="40" y="602" width="108" height="26" rx="4" class="nd"/>')
text(160, 620, "A · about 1,300 characters", "s")
out.append('<rect x="40" y="640" width="500" height="26" rx="4" class="nd"/>')
text(552, 658, "B and C · about 6,000 (up to 24,000)", "s")
box(820, 572, 700, 120, "Our checks on the same filings", [
    "the answers are in the fixed index: 19 kept chunks hold “Total net sales” and “391,035”",
    "offline re-run of A's search: for all 8 figure questions, no chunk with the figure and its",
    "label in the top 3 (first at rank 5–137); the top 3 are 10-K prose, not noise",
    "bge and FlashRank read 512 tokens: ~2,000 characters of prose, fewer of a table"], cls="repb")
svg_ch, H_CH = done(712)

# ================================================================ 7 · sequence: one question through set-up C
out, P = [], "sq"
LIFE = [("cell 51", "test answers", 104), ("rag_answer()", "cell 49", 300), ("retrieve_with_rerank()", "cell 43", 540),
        ("bge-base", "on the T4", 780), ("Pinecone", "namespace 'semantic'", 1000), ("FlashRank", "ONNX, CPU", 1200),
        ("OpenAI", "gpt-4o-mini", 1420)]
SEQ_END = 720
for name, sub, x in LIFE:
    out.append(f'<rect x="{x - 92}" y="24" width="184" height="50" rx="8" class="ep"/>')
    text(x, 46, name, "t2", "middle")
    text(x, 63, sub, "m", "middle")
    out.append(f'<path d="M{x} 74 V{SEQ_END}" class="life"/>')
X = {n: x for n, _, x in LIFE}
out.append(f'<rect x="294" y="116" width="12" height="{640 - 116}" class="act"/>')
out.append(f'<rect x="534" y="156" width="12" height="{448 - 156}" class="act"/>')


def msg(a, b, y, s, ret=False, n=None):
    x1, x2 = X[a] + (6 if X[b] > X[a] else -6), X[b] + (-6 if X[b] > X[a] else 6)
    fl(f"M{x1} {y} H{x2}", "ret" if ret else "ln")
    text((x1 + x2) / 2, y - 7, s, "msg" if not ret else "lbl", "middle")
    fits(s, abs(x2 - x1) + 60, "msg", "sequence")
    if n:
        out.append(f'<rect x="{X["OpenAI"] + 20}" y="{y - 13}" width="{14 + 6.6 * len(n)}" height="19" rx="9.5" '
                   f'class="llm"/>')
        text(X["OpenAI"] + 27 + 3.3 * len(n), y + 1, n, "llmt", "middle")


def self_msg(who, y, s):
    x = X[who] + 6
    out.append(f'<path d="M{x} {y} H{x + 40} V{y + 16} H{x + 2}" class="ln" marker-end="url(#{P}ar)"/>')
    text(x + 48, y + 12, s, "msg")


msg("cell 51", "rag_answer()", 116, "rag_answer(q, use_reranker=True)")
msg("rag_answer()", "retrieve_with_rerank()", 156, "retrieve_with_rerank(query, 10, 3)")
msg("retrieve_with_rerank()", "bge-base", 196, "embed_query(query)")
msg("bge-base", "retrieve_with_rerank()", 220, "768 numbers", ret=True)
msg("retrieve_with_rerank()", "Pinecone", 256, "query(namespace 'semantic', top_k 10)")
msg("Pinecone", "retrieve_with_rerank()", 282, "10 matches: text + source", ret=True)
msg("retrieve_with_rerank()", "FlashRank", 322, "rerank(RerankRequest(query, 10 passages))")
self_msg("FlashRank", 340, "one batch of 10 pairs")
text(1254, 384, "512 tokens each, sorted", "lbs")
msg("FlashRank", "retrieve_with_rerank()", 404, "10 results, best score first", ret=True)
self_msg("retrieve_with_rerank()", 420, "keep the top 3; metadata['rerank_score'] = score")
msg("retrieve_with_rerank()", "rag_answer()", 466, "3 Documents", ret=True)
self_msg("rag_answer()", 492, "format_context: join the 3 texts with '---'")
msg("rag_answer()", "OpenAI", 552, "one user message: rules + 3 chunks + question", n="1")
msg("OpenAI", "rag_answer()", 580, "the answer, plain text", ret=True)
msg("rag_answer()", "cell 51", 636, "{answer, sources}", ret=True)
for i, line in enumerate((
        "use_reranker=False would call retrieve_no_rerank(query, k=3) instead (set-up B's retrieval); no cell does.",
        "Cell 55 never calls rag_answer: it repeats these steps inline for A (retrieve_fixed, k=3, namespace 'fixed'),",
        "B (retrieve_no_rerank, k=3) and C (retrieve_with_rerank, 10 → 3), then the same prompt and model.")):
    text(1500, SEQ_END + 22 + 16 * i, line, "lbs", "end")
text(1500, SEQ_END + 82, "solid arrow: a call · dashed, open arrow: its reply · numbers: LLM calls", "m", "end")
svg_seq, H_SEQ = done(SEQ_END + 96)

# ================================================================ 8 · context assembly
out, P = [], "pa"
header(20, 28, "GENERATOR · cells 49 and 55 · one call per question and set-up")
PROMPT = [
    "You are a financial analyst assistant. Answer the question",
    "using ONLY the context provided below.",
    "If the context does not contain enough information to answer,",
    "say \"I don't have enough context to answer this.\"",
    "Always cite specific numbers and figures when available.",
    "",
    "Context:",
    "{context}",
    "",
    "Question: {question}",
    "",
    "Answer:"]
out.append(f'<rect x="20" y="44" width="740" height="{56 + 17 * len(PROMPT)}" rx="9" class="humb"/>')
text(36, 66, "USER MESSAGE · the only message: from_template has no system part · line breaks added to fit", "rl")
for i, line in enumerate(PROMPT):
    text(36, 92 + 17 * i, line, "pm")
    fits(line, 700, "pm", "prompt")
text(380, 92 + 17 * 7, "← the 3 chunk texts, joined by a '---' line", "lbs")
YP = 44 + 56 + 17 * len(PROMPT) + 16
box(20, YP, 740, 104, "What {context} carries", [
    "A: three fixed-size chunks, about 1,300 characters · B and C: three semantic chunks, about 6,000",
    "no filing, year or page label is added; a source shows only if a page footer falls inside the chunk",
    "gpt-4o-mini · temperature 0 · StrOutputParser → the answer text"], cls="nt")
header(800, 28, "RAGAS JUDGE · cell 57 · per question and set-up")
box(800, 44, 740, 70, "Each row the judge sees", ["question · answer · contexts (the 3 chunk texts) · ground_truth"],
    cls="repb")
box(800, 130, 740, 88, "Faithfulness · 2 calls", ["call 1: split the answer into statements",
                                                  "call 2: is each statement supported by the contexts?",
                                                  ], cls="sysb", tag="supported ÷ all statements")
box(800, 232, 740, 88, "Context precision · 1 call per chunk", [
    "was this chunk useful for reaching the reference answer?",
    "useful chunks ranked early count more"], cls="sysb", tag="rank-weighted precision")
box(800, 334, 740, 88, "Context recall · 1 call", ["which statements of the reference can be found",
                                                    "in the contexts?"], cls="sysb", tag="found ÷ all statements")
box(800, 436, 740, 88, "The judge", [
    "gpt-4o-mini, temperature 0.01 (set by RAGAS): the generator's own model",
    "about 6 calls per row (5 if an answer yields no statements) · 10 rows per set-up · 3 set-ups",
    "text-embedding-3-small is created but attached to none of them: no embeddings field"], cls="nt")
svg_pa, H_PA = done(max(YP + 104, 524) + 20)

# ================================================================ 9 · threat model
out, P = [], "tm"
TM_BOTTOM = 700
out.append(f'<rect x="226" y="40" width="486" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(242, 62, "TB2 · Google Colab runtime", "tbt")
out.append(f'<rect x="760" y="40" width="244" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(776, 62, "TB3 · third-party services", "tbt")
out.append('<path d="M206 40 V730" class="tbl"/>')
text(200, 56, "TB1", "tbt", "end")
text(200, 72, "browser", "lbs", "end")
person(70, 110, "Notebook user", "in a browser")


def tbox(x, y, w, h, title, lines, threats, cls="bx"):
    box(x, y, w, h, title, lines, cls=cls)
    for k, t in enumerate(threats):
        cx, cy = x + w - 20 - 34 * k, y + h - 14
        out.append(f'<rect x="{cx - 16}" y="{cy - 9}" width="32" height="18" rx="9" class="wb"/>')
        text(cx, cy + 4, t, "wbt", "middle")


tbox(246, 90, 446, 160, "Notebook kernel", ["59 cells; filing text and questions go into prompts;",
                                            "filing text into Pinecone, questions only as query",
                                            "vectors; answers only printed in the notebook"],
     ["T8", "T7", "T3"], cls="nd")
tbox(246, 280, 200, 80, "Colab Secrets", ["3 API keys"], ["T9"], cls="cf")
tbox(486, 280, 206, 80, "Disk", ["sec-edgar-filings/", "no checksums"], ["T2"], cls="dt")
tbox(246, 390, 446, 84, "Local models", ["bge-base (PyTorch) · FlashRank (ONNX)", "no pinned revision"], ["T1"])
tbox(246, 500, 446, 70, "Installed packages", ["15 packages via pip, no versions"], ["T1"])
tbox(780, 90, 204, 96, "OpenAI API", ["questions + chunk text,", "twice: answer and judge"], ["T10", "T3"], cls="ex")
tbox(780, 200, 204, 90, "Pinecone", ["stores chunk text", "delete_all on upload"], ["T5", "T3"], cls="ex")
tbox(780, 306, 204, 70, "SEC EDGAR", ["a made-up contact email"], ["T6"], cls="ex")
tbox(780, 392, 204, 70, "Hugging Face Hub", ["model downloads"], ["T1"], cls="ex")
tbox(780, 478, 204, 70, "PyPI", ["packages at every start"], ["T1"], cls="ex")
tbox(780, 584, 204, 84, "GitHub repository", ["notebook committed", "with its outputs"], ["T4"], cls="ex")
fl("M110 130 H244")
text(200, 122, "runs cells,", "lbs", "end")
text(200, 146, "questions", "lbs", "end")
fl("M244 200 H110")
text(200, 216, "answers, outputs", "lbs", "end")
fl("M694 115 H778", "lnr")
text(736, 108, "prompts", "lbs", "middle")
fl("M778 150 H694", "lnr")
text(736, 143, "answers", "lbs", "middle")
fl("M694 215 H778", "lnr")
text(736, 208, "upsert", "lbs", "middle")
fl("M778 245 H694", "lnr")
text(736, 238, "chunks", "lbs", "middle")
fl("M778 330 H694", "lnr")
text(736, 323, "filings", "lbs", "middle")
fl("M778 425 H694", "lnr")
text(736, 418, "weights", "lbs", "middle")
fl("M778 520 H694", "lnr")
text(736, 513, "packages", "lbs", "middle")
fl("M70 212 V722 H880 V670", "lnr")
text(470, 716, "the notebook, with outputs, committed to git", "lbs", "middle")
out.append('<rect x="260" y="580" width="420" height="34" rx="8" class="nt"/>')
text(272, 596, "Red arrows: data crossing TB3, to or from a third party", "m")
text(272, 609, "TB1 browser → Colab · TB2 Google's runtime · TB3 outside services", "m")
THREATS = [
    ("T1", "Tampering · supply chain", "15 packages installed unpinned at every start; models pulled",
     "with no pinned revision, FlashRank's from its author's repo.", "today: none"),
    ("T2", "Tampering · data integrity", "limit=2 fetches whatever is latest; filings are neither pinned",
     "nor checksummed, so the corpus can change between runs.", "today: none"),
    ("T3", "Information disclosure · third parties", "Chunk text and questions go to OpenAI; chunk text is stored",
     "in Pinecone (AWS us-east-1): fine for 10-Ks, not for loan files.", "today: public data only"),
    ("T4", "Information disclosure · committed outputs", "Outputs with filing text and answers are committed;",
     "with client documents that leaks into the git history.", "today: none"),
    ("T5", "Tampering · index control", "Every upload runs delete_all on a namespace; anyone with",
     "the Pinecone key can wipe or alter the experiment's data.", "today: none"),
    ("T6", "Denial of service · blocked by EDGAR", "The downloader declares test@example.com; EDGAR's fair-",
     "access policy asks for a real contact and may block the IP.", "today: none"),
    ("T7", "Tampering · prompt injection", "Filing text, including JSON and viewer-page script, is pasted",
     "into the prompt: low risk for 10-Ks, real for customer files.", "today: the “ONLY the context” rule"),
    ("T8", "Repudiation · no audit trail", "Questions, chunks and answers are only printed; nothing",
     "records who asked what, or which filings answered.", "today: none"),
    ("T9", "Information disclosure · secrets", "Cell 8 copies 3 keys into os.environ, readable by any of the",
     "15 unpinned packages (T1); the HF token goes where nothing reads.", "today: Colab Secrets"),
    ("T10", "Denial of service · cost", "No budget or rate limit; the notebook sets no generator timeout;",
     "the judge makes ~180 calls, up to 10 attempts each on rate limits.", "today: RAGAS's 180 s judge timeout"),
]
out.append(f'<rect x="1040" y="40" width="500" height="{TM_BOTTOM - 40}" rx="12" class="nt"/>')
text(1056, 64, "Threats (STRIDE) and what the notebook does today", "t2")
for i, (tid, title, a, b, today) in enumerate(THREATS):
    yy = 92 + 62 * i
    out.append(f'<rect x="1054" y="{yy - 13}" width="34" height="18" rx="9" class="wb"/>')
    text(1071, yy, tid, "wbt", "middle")
    text(1096, yy, title, "t3")
    text(1096, yy + 15, a, "m")
    text(1096, yy + 29, b, "m")
    text(1096, yy + 43, today, "mi")
    for s, cls in ((a, "m"), (b, "m"), (title, "t3")):
        fits(s, 430, "m", tid)
svg_tm, H_TM = done(TM_BOTTOM + 44)

# ================================================================ 10 · the comparison
out, P = [], "ev"
box(14, 40, 290, 150, "eval_dataset · 10 questions", ["8 reported FY2024 figures", "2 narrative: supply chain,",
                                                       "gross margin", "reference answers, no source"],
    tag="cell 53", cls="dt")
box(350, 30, 290, 62, "A · fixed, top 3", ["retrieve_fixed(q, k=3)"], cls="ep")
box(350, 102, 290, 62, "B · semantic, top 3", ["retrieve_no_rerank(q, k=3)"], cls="ep")
box(350, 174, 290, 62, "C · semantic, top 10 → best 3", ["retrieve_with_rerank(q, 10, 3)"], cls="ep")
for yy in (61, 133, 205):
    fl(f"M304 115 H327 V{yy} H348")
box(690, 70, 240, 130, "Same prompt and model", ["gpt-4o-mini, temperature 0", "3 lists × 10 rows:",
                                                 "question, answer,", "contexts, ground_truth"], cls="nd")
for yy in (61, 133, 205):
    fl(f"M640 {yy} H665 V135 H688")
box(970, 70, 230, 130, "RAGAS evaluate()", ["judge: gpt-4o-mini", "faithfulness · context", "precision · context recall",
                                             "about 6 calls a row"], tag="cell 57", cls="nd")
fl("M930 135 H968")
fl("M1200 135 H1238")
ROWS = [("", "A", "B", "C"), ("Faithfulness", "0.75", "1.000", "0.988"), ("Context precision", "0.00", "0.725", "0.950"),
        ("Context recall", "0.00", "0.775", "1.000")]
out.append('<rect x="1240" y="40" width="300" height="190" rx="9" class="repb"/>')
text(1252, 62, "Results · cell 59, one run", "t2")
for r, row in enumerate(ROWS):
    yy = 92 + 32 * r
    for c, val in enumerate(row):
        xx = 1252 if c == 0 else 1390 + 52 * (c - 1)
        text(xx + (0 if c == 0 else 22), yy, val, "t3" if r == 0 or c == 0 else "s", "start" if c == 0 else "middle")
box(14, 260, 500, 166, "What changes between set-ups", [
    "A → B: boundaries; size (431 against about 2,000 characters);",
    "text handed to the model (~1,300 against ~6,000); which text",
    "the filter drops; how much of each chunk bge's 512 tokens see",
    "B → C: the reranker only (top 10 → best 3)",
    "so only B → C isolates one change"], cls="nt")
box(534, 260, 500, 166, "Not measured", [
    "spread over repeated runs · per-question results (computed,",
    "not shown) · answer correctness (nothing scores it)",
    "whether the expected section was retrieved",
    "exact match for the figures · latency and cost",
    "FY2025, cross-year, calculation or unanswerable questions",
    "a judge from another model family"], cls="nt", step=15)
box(1054, 260, 486, 166, "Our offline checks", [
    "counts reproduce exactly (whole text): 14,119 → 12,142, avg 431",
    "the answers are in the fixed index with their row labels",
    "offline re-run of A's search: no figure + label in any top 3",
    "(first at rank 5–137); the top 3 are 10-K prose, not noise",
    "so for the 8 figure questions, A's 0.00 is a ranking failure"], cls="repb")
svg_ev, H_EV = done(446)

# ================================================================ 11 · the recommended architecture
out, P = [], "rc"
header(20, 28, "WHAT AN FDE WOULD BUILD · the number in a corner is the 2.5 decision that part answers")
text(20, 52, "INGEST, ONCE PER PINNED FILING SET", "rl")
box(20, 70, 200, 120, "EDGAR filings", ["pinned by accession", "number; the 10-K", "document only"], cls="ex", tag="2, 3")
box(250, 70, 210, 120, "Table-aware parser", ["rows keep their", "column headers and", "the table title"], cls="nd",
    tag="4, 6")
box(490, 70, 230, 120, "Chunks + metadata", ["company, form, fiscal", "year, section, page,", "column period;",
                                              "splitter: the comparison's pick"], cls="nd", tag="9")
box(750, 70, 220, 120, "Embed", ["bge; chunks inside", "512 tokens; query", "instruction if it", "measures better"],
    cls="nd", tag="7")
box(1000, 70, 250, 120, "Vector store", ["inside the bank's cloud;", "versioned index per", "filing set"], cls="dt",
    tag="8")
for x in (222, 462, 722, 972):
    fl(f"M{x} 130 H{x + 26}")
box(1280, 70, 260, 120, "Governance", ["MRM validation, AI governance", "and vendor approvals;",
                                       "loan or claims files: OCR,", "redaction, access control first"], cls="nt",
    tag="1")
text(20, 252, "ANSWER A QUESTION", "rl")
fl("M1060 192 V262 H480 V288")
label(770, 256, "chunks for the asked fiscal year", "middle")
person(60, 330, "Analyst", "signed in")
box(120, 320, 200, 120, "Question router", ["figures → XBRL lookup", "narrative → retrieve"], cls="nd", tag="14")
fl("M86 375 H118")
box(360, 290, 240, 90, "Retrieve", ["filter by fiscal year", "(as-reported or latest);", "fixed character budget"],
    cls="nd", tag="9, 10")
box(640, 290, 210, 90, "Rerank", ["a window that fits", "the chunk length"], cls="nd", tag="11")
box(890, 290, 240, 90, "Generate", ["pinned model snapshot;", "cites filing, year, page"], cls="nd", tag="12, 13")
box(360, 430, 240, 80, "XBRL lookup", ["concept, period and", "dimension from the filing"], cls="nd", tag="14")
box(1170, 290, 260, 220, "Answer", ["a figure with its tagged", "source, or narrative", "text with citations,",
                                    "or “not in the filings”"], cls="nd")
fl("M322 350 H340 V335 H358")
fl("M322 410 H340 V470 H358")
fl("M602 335 H638")
fl("M852 335 H888")
fl("M1132 335 H1168")
fl("M602 470 H1168")
fl("M1432 400 H1472")
person(1500, 372, "Analyst", "same person")
box(360, 540, 240, 48, "XBRL fact table", [], cls="dt", tag="14")
fl("M480 538 V512")
fl("M20 150 H8 V564 H358")
label(200, 558, "the filing's XBRL instance", "middle")
box(20, 610, 1520, 90, "Evaluation and operations", [
    "set-ups: fixed 512 and about 2,000 characters, and semantic, each with and without the reranker; golden set of "
    "30–50 analyst questions with expected answer and section, signed off by a finance SME, a third held out",
    "deterministic checks first: expected section at a fixed character budget, exact figure match; RAGAS judge "
    "calibrated on human labels; three runs per set-up and a written decision rule",
    "every result stored; a pinned pipeline, a runbook, scheduled ingestion and evaluation"], cls="nt",
    tag="5, 11, 15, 16")
svg_rc, H_RC = done(716)

# ================================================================ page
FIGS = [
    ("context", "System context", "Before anything else: what the system is, who uses it, and what it depends on.",
     svg_ctx, 1560, H_CTX,
     "System context: a notebook user runs the Financial RAG notebook on Google Colab; it downloads two Apple 10-K "
     "submissions from SEC EDGAR, model weights from the Hugging Face Hub and packages from PyPI, stores vectors in "
     "its own Pinecone index and calls the OpenAI API to answer and to judge."),
    ("architecture", "High-level architecture", "Then the parts and where they run: the Colab runtime or cloud APIs.",
     svg_ar, 1560, H_AR,
     "High-level architecture: inside the Colab runtime, ingestion downloads, cleans, chunks two ways, embeds and "
     "uploads; the question path retrieves, reranks, generates and evaluates; bge-base runs on the T4 GPU and "
     "FlashRank on the CPU; Pinecone and OpenAI are cloud services."),
    ("dataflow", "Data flow (level 1)", "Then what data moves between those parts, and where it is stored.",
     svg_dfd, 1560, H_DFD,
     "Level-1 data flow: filings flow from SEC EDGAR through download, cleaning and two chunkers into two Pinecone "
     "namespaces; questions flow through retrieval, reranking and generation; evaluation sends answers and chunks "
     "to the OpenAI judge and returns the score table."),
    ("datamodel", "Data model", "Then the exact shape of each piece of data in those flows.",
     svg_dm, 1560, H_DM,
     "Data model: the EDGAR file, LangChain Documents and chunks, Pinecone records, retrieved chunks, FlashRank "
     "requests and results, rag_answer results, evaluation questions, results rows and RAGAS scores, and the "
     "settings."),
    ("design", "Detailed design: the notebook", "Then every cell, function and setting, with what is broken.",
     svg_design, 1560, H_DESIGN,
     "Detailed design: the notebook's nine sections with their cells, functions and settings, and ten numbered "
     "review notes, from the undefined header function to the unpinned packages."),
    ("chunking", "The two chunking paths", "Then the comparison the brief asks for: the same text, cut two ways.",
     svg_ch, 1560, H_CH,
     "The two chunking paths: most of the indexed text is not the 10-K; fixed-size cuts at 512 characters and "
     "filters to 12,142 chunks; semantic chunking splits sentences, cuts at the 65th percentile of distances and "
     "ends with 2,529 chunks; top 3 hands the model about 1,300 or 6,000 characters."),
    ("sequence", "Sequence: one question", "Then one request through set-up C, call by call, in time order.",
     svg_seq, 1560, H_SEQ,
     "Sequence of one question as cell 51 runs set-up C: rag_answer calls retrieve_with_rerank, which embeds the "
     "question, queries Pinecone for 10 chunks and has FlashRank score them in one batch, keeping the best 3; "
     "rag_answer makes one OpenAI call. Notes cover set-up B and the evaluation loop."),
    ("prompts", "Context assembly", "Then exactly what the generator and the judge are sent.",
     svg_pa, 1560, H_PA,
     "Context assembly: the generator gets one user message with the rules, three chunks and the question; the "
     "RAGAS judge gets the question, answer, contexts and reference, and makes about six calls per row (five if an answer yields no statements)."),
    ("threats", "Threat model", "With all of that drawn: where it could be attacked, and what protects it today.",
     svg_tm, 1560, H_TM,
     "Threat model: trust boundaries between the browser, the Colab runtime and third-party services; ten STRIDE "
     "threats, from unpinned packages to OpenAI calls with no budget or rate limit, each marked on the part it affects."),
    ("evaluation", "The comparison: A, B and C", "Then what the three set-ups change, and what the scores can show.",
     svg_ev, 1560, H_EV,
     "The comparison: ten questions run through set-ups A, B and C with the same prompt and model, scored by RAGAS; "
     "what changes between set-ups, what is not measured, and what our offline checks found."),
    ("recommended", "The recommended architecture", "Finally: the design an FDE would build, with the 2.5 decision each numbered part answers.",
     svg_rc, 1560, H_RC,
     "The recommended architecture: pinned 10-K documents parsed with tables intact, chunked with metadata and embedded into a versioned store in the bank's cloud; a router sends figure questions to an XBRL lookup and narrative questions through retrieval, reranking and a pinned generator that cites its sources; governance and evaluation run alongside."),
]
FDE = Path(__file__).with_name("fde_2b.html").read_text(encoding="utf-8")
for tok in ("us-east-1", "fail-open", "in-house", "top-k", "top-3", "re-ranked", "re-run", "re-runs", "gpt-4o-mini",
            "bge-base-en-v1.5", "ms-marco-MiniLM-L-12-v2", "full-submission.txt", "year-on-year", "512-token",
            "cross-encoder", "text-embedding-3-small", "10-K/A"):
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
  <p class="lede">Eleven diagrams in the order a design is reasoned out: scope, parts, data, the notebook itself, the
    chunking comparison, behaviour, risk and the evidence, then the design an FDE would build instead. Each answers a group of the questions above (see 2.9).</p>
</section>"""
PFX = {'context': 'cx', 'architecture': 'ar', 'dataflow': 'df', 'datamodel': 'dm', 'design': 'ds',
       'chunking': 'ch', 'sequence': 'sq', 'prompts': 'pa', 'threats': 'tm', 'evaluation': 'ev', 'recommended': 'rc'}
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
        "<title>2B: Brief to Architecture</title>\n<style>\n" + CSS + "\n</style>\n</head>\n<body>\n<header>\n"
        "  <p class=\"eyebrow\">Requirement → FDE analysis → architecture · The Gen Academy · Week 2, project 2B</p>\n"
        "  <h1>Financial Document Intelligence Pipeline</h1>\n"
        "  <p class=\"src\">Drawn from the notebook at commit <a href=\"https://github.com/The-Gen-Academy/"
        "2B-Financial-Document-Intelligence-Pipeline/tree/39d2249c8135d24af99e99d2a6c33488ad2f6dc0\">39d2249</a>, "
        "its saved outputs, and the <a href=\"https://docs.google.com/document/d/1QyqbNCXxlwfuvqAkR74GSfs7rPfF4NaG/"
        "edit\">solution kit</a>.</p>\n</header>\n" + nav + "\n" + body + "\n</body>\n</html>\n")
OUT.write_text(page, encoding="utf-8")
print("written:", OUT, len(FIGS), "figures")
for w in warnings:
    print("WARN", w)
