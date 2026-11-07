"""Writes the architecture page of The Gen Academy's 2A Enterprise Q&A Bot (diagram only) as one self-contained HTML
file. Usage: make_2a.py OUT_HTML. Warns when a line is likely too long for its box."""
import re
import sys
from html import escape
from pathlib import Path

OUT = Path(sys.argv[1])
W, H = 1560, 1530
LX, LW = 20, 450          # left: ingestion, Pinecone, configuration
MX, MW = 520, 360         # middle: the LangGraph graph
SX, SW = 915, 175         # side: the two loops
RX, RW = 1120, 420          # right: callers, state, services, notes
CHAR = {"t": 7.6, "s": 6.5, "m": 6.3}
out, warnings = [], []


def text(x, y, s, cls, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>')


def fits(s, width, cls, where):
    if len(s) * CHAR.get(cls, 6.5) > width:
        warnings.append(f"{where}: {len(s)} chars may overflow {width}px: {s}")


def box(x, y, w, h, title, lines=(), cls="bx", tag=None, llm=None, warn=(), lcls="s", step=16):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" class="{cls}"/>')
    text(x + 12, y + 22, title, "t")
    fits(title, w - 24 - (90 if llm else 0), "t", title)
    for i, line in enumerate(lines):
        text(x + 12, y + 42 + step * i, line, lcls)
        fits(line, w - 24, lcls, title)
    if tag:
        text(x + w - 12, y + h - 10, tag, "tag", "end")
    if llm:
        bw = 14 + 6.6 * len(llm)
        out.append(f'<rect x="{x + w - bw - 10}" y="{y + 8}" width="{bw}" height="19" rx="9.5" class="llm"/>')
        text(x + w - 10 - bw / 2, y + 22, llm, "llmt", "middle")
    for i, n in enumerate(warn):
        cx = x + w - 16 - 24 * i - (0 if not tag else 0)
        cy = y + h - (34 if tag else 16)
        out.append(f'<circle cx="{cx}" cy="{cy}" r="9.5" class="wb"/>')
        text(cx, cy + 4, str(n), "wbt", "middle")


def pill(x, y, w, h, s, cls="pl"):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" class="{cls}"/>')
    text(x + w / 2, y + h / 2 + 4.5, s, "pt", "middle")
    fits(s, w - 20, "s", "pill")


def path(d, cls="ln", marker="ar"):
    end = f' marker-end="url(#{marker})"' if marker else ""
    out.append(f'<path d="{d}" class="{cls}"{end}/>')


def label(x, y, s, anchor="start", cls="lbl"):
    text(x, y, s, cls, anchor)


def diamond(cx, cy, hw, hh, s):
    out.append(f'<path d="M{cx - hw} {cy} L{cx} {cy - hh} L{cx + hw} {cy} L{cx} {cy + hh} Z" class="dm"/>')
    text(cx, cy + 4.5, s, "dmt", "middle")


def cylinder(x, y, w, h, title, sub):
    ry = 9
    out.append(f'<path d="M{x} {y + ry} A{w / 2} {ry} 0 0 1 {x + w} {y + ry} L{x + w} {y + h - ry} '
               f'A{w / 2} {ry} 0 0 1 {x} {y + h - ry} Z" class="cy"/>')
    out.append(f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}" class="cyt"/>')
    text(x + w / 2, y + h / 2 + 6, title, "t", "middle")
    text(x + w / 2, y + h / 2 + 24, sub, "s", "middle")


def header(x, y, s, sub):
    text(x, y, s, "h")
    text(x, y + 18, sub, "hs")


# ---------------------------------------------------------------- left: ingestion
header(LX, 28, "① INGESTION · offline, run once", "python -m src.ingestion → ingest_all() · src/ingestion.py")
box(LX, 62, LW, 100, "Step 1 · create_pinecone_index()", [
    "Pinecone(api_key).list_indexes()",
    "missing → create_index('enterprise-rag', dimension=384,",
    "metric='cosine', spec=ServerlessSpec('aws', 'us-east-1'))",
    "then polls describe_index().status['ready'] every 3 s"])
path(f"M{LX + LW / 2} 162 V188")
label(LX + LW / 2 + 10, 180, "then, once")
box(LX, 190, LW, 88, "get_embeddings() · built once, before the loop", [
    "HuggingFaceEmbeddings('sentence-transformers/all-MiniLM-L6-v2')",
    "→ 384 numbers · device='cpu' · normalize_embeddings=True",
    "no API key · ~90 MB from Hugging Face once, then cached"])
path(f"M{LX + LW / 2} 278 V304")
label(LX + LW / 2 + 10, 296, "then, for each of the 3 folders")
box(LX, 306, LW, 104, "docs/ · 3 folders = 3 namespaces", [
    "hr/hr_policy.txt · 5.8 KB · 10 numbered sections",
    "technical/tech_docs.txt · 6.5 KB · 9 sections",
    "compliance/compliance_manual.txt · 7.6 KB · 7 sections",
    "made-up ACME Corporation manuals, plain text"], cls="dt")
path(f"M{LX + LW / 2} 410 V436")
label(LX + LW / 2 + 10, 428, "files")
box(LX, 438, LW, 104, "load_documents_from_folder(folder, doc_type)", [
    ".txt → TextLoader(encoding='utf-8') · .pdf → PyPDFLoader (pypdf)",
    "other files skipped · a missing folder → warning, skipped",
    "1 file = 1 Document (a PDF: 1 Document per page)",
    "metadata: doc_type = folder name · source = file name"])
path(f"M{LX + LW / 2} 542 V568")
label(LX + LW / 2 + 10, 560, "1 Document per file")
box(LX, 570, LW, 88, "chunk_documents() · RecursiveCharacterTextSplitter", [
    "chunk_size 512 characters · chunk_overlap 64",
    "separators: \\n\\n · \\n · '.' · ' ' · ''",
    "17 + 18 + 20 = 55 chunks (measured; longest 510 characters)"], warn=(7,))
path(f"M{LX + LW / 2} 658 V684")
label(LX + LW / 2 + 10, 676, "chunks, each with doc_type and source")
box(LX, 686, LW, 74, "PineconeVectorStore.from_documents()", [
    "embeds with the model built once above, then upserts",
    "into namespace = doc_type · random uuid4 ids, nothing deleted"], warn=(4,))
path(f"M{LX} 723 H6 V490 H{LX - 2}", cls="lnc", marker="arc")
out.append(f'<text x="15" y="606" class="lblc" text-anchor="middle" transform="rotate(-90 15 606)">next folder</text>')
path(f"M{LX + LW / 2} 760 V790")
label(LX + LW / 2 + 10, 780, "upsert: vector + text + metadata")

# Pinecone
out.append(f'<rect x="{LX}" y="792" width="{LW}" height="196" rx="12" class="pc"/>')
text(LX + 14, 816, "Pinecone serverless index 'enterprise-rag'", "t")
text(LX + 14, 834, "384 dimensions · cosine · AWS us-east-1 · PINECONE_API_KEY", "s")
for i, (ns, n) in enumerate((("hr", 17), ("technical", 18), ("compliance", 20))):
    cylinder(LX + 22 + i * 142, 850, 122, 100, ns, f"{n} chunks")
text(LX + 14, 976, "each record: vector + chunk text + {doc_type, source}", "s")

# ---------------------------------------------------------------- left: configuration
header(LX, 1022, "④ CONFIGURATION", "src/config.py · .env (load_dotenv at import)")
box(LX, 1054, LW, 88, ".env", [
    "LLM_PROVIDER = groq (default); any other value → OpenAI",
    "GROQ_API_KEY · OPENAI_API_KEY · PINECONE_API_KEY",
    "PINECONE_INDEX_NAME = enterprise-rag"], cls="cf")
box(LX, 1156, LW, 72, "Constants", [
    "PINECONE_DIMENSION 384 · NAMESPACES [hr, technical, compliance]",
    "TOP_K_PER_NAMESPACE 4 · TOP_K_GENERAL 2 · MAX_RETRIES 2"], cls="cf")
box(LX, 1242, LW, 104, "get_llm(temperature=0) · used by every LLM node", [
    "groq → ChatGroq('llama-3.3-70b-versatile')",
    "anything else → ChatOpenAI('gpt-4o-mini')",
    "a new client in every node run; no timeout or retry set",
    "get_active_provider() → the label in the sidebar"], cls="cf", warn=(8,))
box(LX, 1360, LW, 88, "requirements.txt · 13 packages, none pinned", [
    "langchain, langgraph, langchain-groq, langchain-openai,",
    "langchain-pinecone, langchain-huggingface, langchain-community,",
    "sentence-transformers, pinecone-client, streamlit, pypdf, …"],
    cls="cf", warn=(9,))

# ---------------------------------------------------------------- middle: the graph
header(MX, 28, "② QUERY TIME · LangGraph", "StateGraph(RAGState) · src/graph.py · compiled once (_get_graph)")
pill(MX, 62, MW, 34, "START · run_query(question) · retry_count = 0")
path(f"M{MX + MW / 2} 96 V124")
box(MX, 126, MW, 118, "router · route_question()", [
    "hr | technical | compliance | general",
    "the prompt lists each category's topics;",
    "reply = one lowercase word",
    "any other reply → 'general'",
    "writes: doc_type"], cls="nd", llm="LLM ×1", tag="src/nodes/router.py")
path(f"M{MX + MW / 2} 244 V274")
label(MX + MW / 2 + 10, 263, "doc_type")
box(MX, 276, MW, 138, "retriever · retrieve_documents()", [
    "embeds the question with MiniLM, then",
    "similarity_search (no scores) · 0 LLM calls",
    "hr | technical | compliance → that namespace, k 4",
    "general → each namespace, k 2 → 6 chunks,",
    "joined in the order hr, technical, compliance",
    "writes: documents"], cls="nd", tag="src/nodes/retriever.py", warn=(5,))
path(f"M{MX + MW / 2} 414 V444")
label(MX + MW / 2 + 10, 433, "4 or 6 chunks")
box(MX, 446, MW, 138, "grader · grade_documents()", [
    "asks 'relevant?' for each chunk, one by one",
    "'be generous' → JSON {score: yes | no}",
    "chunk text cut at 1,500 characters",
    "any error (bad JSON or a failed call) → kept",
    "writes: documents = the 'yes' chunks,",
    "grading_result"], cls="nd", llm="LLM × chunks", tag="src/nodes/grader.py", warn=(6, 7))
path(f"M{MX + MW / 2} 584 V606")
diamond(MX + MW / 2, 632, 122, 26, "decide_after_grading")
path(f"M{MX + MW / 2} 658 V700", cls="lnc", marker="arc")
label(MX + MW / 2 + 10, 683, "a chunk kept, or retry_count ≥ 2", cls="lblc")

# retry loop
box(SX, 446, SW, 150, "retry_retrieve", [
    "widen_and_retrieve()",
    "doc_type = 'general'",
    "retry_count + 1",
    "retrieve_documents()",
    "again: k 2 × 3 = 6",
    "→ back to the grader"], cls="lp", lcls="m", tag="a node · graph.py:88", warn=(3,))
path(f"M{MX + MW / 2 + 122} 632 H{SX + SW / 2} V598", cls="lnc", marker="arc")
label(MX + MW / 2 + 130, 624, "no chunk kept,", cls="lblc")
label(MX + MW / 2 + 130, 650, "retry_count < 2", cls="lblc")
path(f"M{SX} 515 H{MX + MW + 2}", cls="lnc", marker="arc")

box(MX, 702, MW, 150, "generator · generate_answer()", [
    "system: ACME assistant; answer only",
    "from the context; too little → the fixed",
    "\"I couldn't find a definitive answer in the",
    "knowledge base…\"; no file names; no made-up",
    "numbers, dates or policies",
    "context: chunk texts joined by '---', no titles",
    "writes: generation"], cls="nd", llm="LLM ×1", tag="src/nodes/generator.py")
path(f"M{MX + MW / 2} 852 V882")
label(MX + MW / 2 + 10, 871, "the answer")
box(MX, 884, MW, 154, "checker · check_hallucination()", [
    "'is every claim in these chunks?' → yes | no",
    "sees the chunks (each cut at 800) and the",
    "answer, not the question",
    "no chunks, or retry_count ≥ 2 → 'grounded'",
    "without an LLM call · any error → 'grounded'",
    "writes: hallucination_result, retry_count + 1"],
    cls="nd", llm="LLM ×1 or 0", tag="src/nodes/checker.py", warn=(1, 6))
path(f"M{MX + MW / 2} 1038 V1060")
diamond(MX + MW / 2, 1086, 126, 26, "decide_after_checking")
path(f"M{MX + MW / 2} 1112 V1150", cls="lnc", marker="arc")
label(MX + MW / 2 + 10, 1135, "grounded, or retry_count ≥ 2", cls="lblc")
pill(MX, 1152, MW, 34, "END · the final RAGState goes back to the caller", cls="pl")

# regenerate: an edge back to the generator, not a node
path(f"M{MX + MW / 2 + 126} 1086 H{SX + SW / 2} V790 H{MX + MW + 2}", cls="lnc", marker="arc")
label(MX + MW / 2 + 134, 1078, "not grounded,", cls="lblc")
label(MX + MW / 2 + 134, 1104, "retry_count < 2", cls="lblc")
for i, line in enumerate(("regenerate:", "an edge back to", "the generator,", "not a node;",
                          "same prompt and", "chunks, temp. 0")):
    label(SX + SW / 2 + 10, 850 + 16 * i, line, cls="lblc")
out.append(f'<circle cx="{SX + SW / 2 + 22}" cy="{850 + 16 * 6 + 8}" r="9.5" class="wb"/>')
text(SX + SW / 2 + 22, 850 + 16 * 6 + 12, "2", "wbt", "middle")

# cost
box(MX, 1214, MW + SW + 35, 118, "Calls per question", [
    "usual: 7 LLM calls = 1 router + 4 grades + 1 answer + 1 check",
    "worst: 20 = 1 router + 6 + 6 + 6 grades + 1 answer",
    "     (out of scope, routed 'general', nothing kept: the check is skipped)",
    "Pinecone queries: 1 (one namespace) up to 9 ('general' + 2 retries)",
    "every LLM call is sequential and synchronous: no batching, no streaming"], cls="ct")

# ---------------------------------------------------------------- right: callers, state, services, notes
header(RX, 28, "③ ENTRY POINTS", "both call run_query(question) · the graph is built on first use")
box(RX, 62, RW, 176, "app.py · Streamlit chat", [
    "st.chat_input → run_query() inside a spinner",
    "answer shown with st.write (Markdown)",
    "'Source Documents': unique file names of the",
    "kept chunks · metrics: Namespace, Retries",
    "history in st.session_state: shown, never sent",
    "sidebar: knowledge base, nodes, active LLM, Clear",
    "an exception → st.error('Pipeline error: …')",
    "hallucination_result is never shown"], cls="ep", warn=(1, 10))
box(RX, 252, RW, 172, "evaluate.py · 15 questions", [
    "HR 4 · Technical 3 · Compliance 3 · Edge cases 5",
    "(cross-document 2, out of scope, ambiguous, trap)",
    "routing: an expected 'general' always passes",
    "answerability: answerable ones always pass;",
    "unanswerable pass on phrases ('couldn't find', …)",
    "records route, chunks kept, retries, latency",
    "→ evaluation_report.json (gitignored)",
    "no retrieval score · expected answers: doc only"], cls="ep")
path(f"M{RX} 110 H{SX + SW + 14} V79 H{MX + MW + 2}")
path(f"M{RX} 300 H{SX + SW + 14} V110", marker=None)
label(SX + SW + 8, 70, "run_query(question)", anchor="end")

out.append(f'<rect x="{RX}" y="446" width="{RW}" height="232" rx="9" class="st"/>')
text(RX + 12, 468, "RAGState · TypedDict · src/state.py", "t")
text(RX + 12, 486, "every node returns {**state, …changes}", "s")
rows = [("question", "run_query; never changed"),
        ("doc_type", "router; retry_retrieve → 'general'"),
        ("documents", "retriever; grader keeps 'yes' chunks"),
        ("grading_result", "grader: relevant | not_relevant"),
        ("generation", "generator"),
        ("hallucination_result", "checker: grounded | not_grounded"),
        ("retry_count", "retry_retrieve and checker, +1 each")]
for i, (f, by) in enumerate(rows):
    y = 512 + 22 * i
    text(RX + 12, y, f, "mf")
    text(RX + 150, y, by, "m")
    fits(by, RW - 162, "m", "state")
out.append(f'<circle cx="{RX + RW - 16}" cy="{512 + 22 * 6 - 4}" r="9.5" class="wb"/>')
text(RX + RW - 16, 512 + 22 * 6, "1", "wbt", "middle")

out.append(f'<rect x="{RX}" y="694" width="{RW}" height="150" rx="9" class="ex"/>')
text(RX + 12, 716, "External services", "t")
for i, (name, what) in enumerate((("Groq API", "llama-3.3-70b-versatile · default"),
                                  ("OpenAI API", "gpt-4o-mini · any other LLM_PROVIDER"),
                                  ("Pinecone", "serverless index · AWS us-east-1"),
                                  ("Hugging Face Hub", "model download only; runs on CPU"))):
    y = 742 + 24 * i
    out.append(f'<circle cx="{RX + 18}" cy="{y - 4}" r="4" class="dot"/>')
    text(RX + 30, y, name, "mf")
    text(RX + 150, y, what, "m")
    fits(what, RW - 162, "m", "services")

NOTES = [
    ("retry_count is shared by both loops: after 2 search retries",
     "the check is skipped, after 1 there's no regeneration, and",
     "the page shows unchecked or failed answers with no warning."),
    ("Regenerating reuses the same prompt and chunks at",
     "temperature 0, so it usually returns the same answer."),
    ("Every retry searches 'general' with the same question:",
     "the 2nd retry, and the 1st if the route was 'general',",
     "repeats the identical search and gets the same 6 chunks."),
    ("Re-running ingestion adds every chunk again: random ids",
     "and nothing deleted, so copies fill the top k."),
    ("HuggingFaceEmbeddings is rebuilt, model reloaded, on every",
     "search: 3 times for a 'general' question."),
    ("Grader and checker fail open: any error, bad JSON or a",
     "failed LLM call, keeps the chunk or passes the answer."),
    ("The 1,500 and 800-character cuts never apply: no chunk",
     "is longer than 510 characters."),
    ("Docstrings say OpenAI embeddings and the README says",
     "llama-3.1; the code uses MiniLM and llama-3.3."),
    ("pinecone-client≥3 resolves to 6.0.0, a stub whose import",
     "raises 'renamed to pinecone'; it shares a folder with the",
     "real pinecone package, so install order decides which wins."),
    ("The checker adds 1 to retry_count on every pass, so the",
     "'Retries' metric shows 1 when nothing was retried."),
]
NOTES_H = 48 + sum(16 * len(n) + 10 for n in NOTES)
out.append(f'<rect x="{RX}" y="860" width="{RW}" height="{NOTES_H}" rx="9" class="nt"/>')
text(RX + 12, 882, "Notes on the build (the numbered badges)", "t")
y = 908
for n, lines in enumerate(NOTES, 1):
    out.append(f'<circle cx="{RX + 20}" cy="{y - 4}" r="9.5" class="wb"/>')
    text(RX + 20, y, str(n), "wbt", "middle")
    for j, line in enumerate(lines):
        text(RX + 38, y + 16 * j, line, "m")
        fits(line, RW - 50, "m", f"note {n}")
    y += 16 * len(lines) + 10

# Pinecone → retriever
path(f"M{LX + LW} 900 H{MX - 24} V345 H{MX - 2}")
out.append(f'<text x="{MX - 10}" y="640" class="lbl" text-anchor="middle" '
           f'transform="rotate(-90 {MX - 10} 640)">similarity_search · cosine · top k</text>')

# legend
LY = 860 + NOTES_H + 22
out.append(f'<rect x="{MX}" y="{LY}" width="{RX + RW - MX}" height="112" rx="9" class="lg"/>')
text(MX + 14, LY + 24, "Legend", "t")
path(f"M{MX + 16} {LY + 48} H{MX + 66}")
text(MX + 76, LY + 52, "fixed edge or data flow", "s")
path(f"M{MX + 16} {LY + 76} H{MX + 66}", cls="lnc", marker="arc")
text(MX + 76, LY + 80, "conditional edge or loop", "s")
out.append(f'<rect x="{MX + 330}" y="{LY + 38}" width="60" height="19" rx="9.5" class="llm"/>')
text(MX + 360, LY + 52, "LLM ×1", "llmt", "middle")
text(MX + 400, LY + 52, "an LLM call (Groq or OpenAI, temperature 0)", "s")
out.append(f'<circle cx="{MX + 360}" cy="{LY + 76}" r="9.5" class="wb"/>')
text(MX + 360, LY + 80, "1", "wbt", "middle")
text(MX + 400, LY + 80, "a note on the right", "s")
text(MX + 14, LY + 102, "Boxes name their file and function; numbers are the code's own settings.", "s")

svg = "\n".join(out)
n_detail = len(out)

# ================================================================ the high-level architecture (what runs where)
out = []
HW, HH = 1560, 640


def person(cx, top, name, sub):
    out.append(f'<circle cx="{cx}" cy="{top + 14}" r="13" class="pa"/>')
    out.append(f'<path d="M{cx - 24} {top + 62} Q{cx - 24} {top + 32} {cx} {top + 32} '
               f'Q{cx + 24} {top + 32} {cx + 24} {top + 62} Z" class="pa"/>')
    text(cx, top + 82, name, "t", "middle")
    text(cx, top + 99, sub, "s", "middle")


def hpath(d, cls="ln", marker="har"):
    path(d, cls, marker)


# Boundaries
out.append('<rect x="232" y="54" width="856" height="560" rx="14" class="bnd"/>')
text(250, 78, "YOUR MACHINE · local Python, one process per command", "h")
out.append(f'<rect x="1110" y="54" width="436" height="420" rx="14" class="bndc"/>')
text(1128, 78, "CLOUD SERVICES · over the internet", "h")
text(1128, 462, "API keys: Pinecone and the LLM; the Hub needs none", "hs")

# People
person(120, 96, "Employee", "asks in the chat")
person(120, 430, "Developer", "runs the scripts")

# Local boxes
box(260, 96, 240, 120, "Streamlit chat UI", [
    "app.py · streamlit run app.py",
    "chat history in the session",
    "shows the answer, source files,",
    "namespace and retry count"], cls="ep")
box(260, 236, 240, 100, "Evaluation script", [
    "evaluate.py · run by hand",
    "15 questions, each via run_query",
    "→ evaluation_report.json"], cls="ep")
box(260, 380, 240, 92, "docs/ · knowledge base", [
    "hr · technical · compliance",
    "3 plain-text manuals, ~20 KB"], cls="dt")

out.append('<rect x="560" y="96" width="450" height="200" rx="9" class="nd"/>')
text(574, 120, "LangGraph RAG pipeline", "t")
text(996, 120, "src/graph.py · src/nodes/", "tag", "end")
chips = ["router", "retriever", "grader", "generator", "checker"]
cw, gap, x0, cy0 = 70, 14, 576, 138
for i, c in enumerate(chips):
    x = x0 + i * (cw + gap)
    out.append(f'<rect x="{x}" y="{cy0}" width="{cw}" height="30" rx="7" class="chip"/>')
    text(x + cw / 2, cy0 + 20, c, "cht", "middle")
    if i:
        hpath(f"M{x - gap} {cy0 + 15} H{x - 1}")
cx = [x0 + i * (cw + gap) + cw / 2 for i in range(5)]
hpath(f"M{cx[2]} {cy0 + 31} Q{(cx[1] + cx[2]) / 2} {cy0 + 70} {cx[1]} {cy0 + 33}", cls="lnc", marker="harc")
text((cx[1] + cx[2]) / 2, cy0 + 72, "retry, wider", "lblc", "middle")
hpath(f"M{cx[4]} {cy0 + 31} Q{(cx[3] + cx[4]) / 2} {cy0 + 70} {cx[3]} {cy0 + 33}", cls="lnc", marker="harc")
text((cx[3] + cx[4]) / 2, cy0 + 72, "regenerate", "lblc", "middle")
text(574, 248, "in-process library, imported by app.py and evaluate.py", "s")
text(574, 266, "RAGState (7 fields) · ~7 LLM calls a question, up to 20", "s")
text(574, 282, "the two loops share one counter; both stop at MAX_RETRIES 2", "s")

box(560, 330, 200, 100, "Configuration", [
    "a file, read at import:",
    ".env + src/config.py",
    "provider, keys, k, retries"], cls="cf")
box(790, 330, 220, 100, "Embedding model", [
    "all-MiniLM-L6-v2 · 384-d",
    "in-process, on the local CPU",
    "HuggingFaceEmbeddings"], cls="bx")
box(260, 500, 520, 92, "Ingestion job · src/ingestion.py · run once by the developer", [
    "create index → load 3 files → chunk 512 / 64 → embed → upsert",
    "55 chunks, one namespace per folder · re-running adds copies"], cls="bx")

# Cloud boxes
out.append('<rect x="1130" y="96" width="396" height="140" rx="9" class="pc"/>')
text(1144, 120, "Pinecone vector database", "t")
text(1144, 140, "serverless index 'enterprise-rag' · AWS us-east-1 · 384-d, cosine", "m")
for i, (ns, n) in enumerate((("hr", 17), ("technical", 18), ("compliance", 20))):
    x, y, w, h, ry = 1146 + i * 126, 156, 112, 66, 7
    out.append(f'<path d="M{x} {y + ry} A{w / 2} {ry} 0 0 1 {x + w} {y + ry} L{x + w} {y + h - ry} '
               f'A{w / 2} {ry} 0 0 1 {x} {y + h - ry} Z" class="cy"/>')
    out.append(f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}" class="cyt"/>')
    text(x + w / 2, y + 38, ns, "cht", "middle")
    text(x + w / 2, y + 55, f"{n} chunks", "m", "middle")
box(1130, 256, 396, 80, "LLM provider · one of", [
    "Groq API · llama-3.3-70b-versatile (default)",
    "OpenAI API · gpt-4o-mini · picked by LLM_PROVIDER"], cls="ex")
box(1130, 356, 396, 80, "Hugging Face Hub", [
    "all-MiniLM-L6-v2 weights, about 90 MB",
    "downloaded on first use, then cached"], cls="ex")

# Connections
hpath("M150 140 H258")
label(204, 132, "question", anchor="middle")
hpath("M258 180 H164")
label(204, 163, "answer + sources", anchor="middle")
hpath("M120 428 V300 H258")
label(190, 292, "python evaluate.py", anchor="middle")
hpath("M150 546 H258")
label(214, 524, "python -m", anchor="middle")
label(214, 538, "src.ingestion", anchor="middle")
hpath("M500 136 H558")
label(529, 128, "run_query", anchor="middle")
hpath("M558 176 H502")
label(529, 193, "result", anchor="middle")
hpath("M500 286 H558")
label(529, 278, "× 15", anchor="middle")
hpath("M1010 130 H1128")
label(1049, 122, "search", anchor="middle")
hpath("M1128 175 H1012")
label(1049, 192, "chunks", anchor="middle")
hpath("M1010 270 H1128")
label(1049, 262, "prompts", anchor="middle")
hpath("M1128 290 H1012")
label(1049, 305, "replies", anchor="middle")
hpath("M900 296 V328")
label(908, 318, "embed the question")
hpath("M1128 396 H1012")
label(1049, 388, "first run", anchor="middle")
hpath("M660 330 V298", cls="lnd")
label(668, 318, "settings")
hpath("M660 430 V498", cls="lnd")
label(668, 470, "keys, index name")
hpath("M380 472 V498")
label(388, 490, "reads")
hpath("M780 522 H900 V432")
label(908, 470, "embed 55 chunks")
hpath("M780 566 H1553 V166 H1528")
label(1160, 558, "create the index, then upsert the chunks: one namespace per folder")

svg_high = "\n".join(out)


# ================================================================ shared helpers for the new figures
def defs(p):
    m = ('<marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0,0 L10,5 L0,10 z" class="{c}"/></marker>')
    return ("<defs>" + m.format(id=p + "ar", c="ah") + m.format(id=p + "arc", c="ahc")
            + m.format(id=p + "arr", c="ahr")
            + f'<marker id="{p}aro" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10" class="aho"/></marker>' + "</defs>")


def fl(d, p, kind="ln"):
    mk = {"ln": "ar", "lnd": "ar", "ret": "aro", "lnc": "arc", "lnr": "arr"}[kind]
    out.append(f'<path d="{d}" class="{kind}" marker-end="url(#{p}{mk})"/>')


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


def ent(x, y, w, h, eid, title, sub="", dup=False):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="ee"/>')
    text(x + w / 2, y + (h / 2 - 3 if sub else h / 2 + 5), f"{eid} · {title}", "t2", "middle")
    if sub:
        text(x + w / 2, y + h / 2 + 14, sub, "m", "middle")
    if dup:
        out.append(f'<path d="M{x} {y + 14} L{x + 14} {y}" class="dupl"/>')


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


# ================================================================ 1 · system context
out = []
P = "cx"
out.append('<path d="M585 8 H1535 V160 H975 V345 H585 Z" class="bnd"/>')
text(1527, 30, "system boundary: the bot, its docs/ and its own Pinecone index", "lbs", "end")
out.append('<rect x="600" y="170" width="360" height="160" rx="12" class="nd"/>')
text(780, 206, "Enterprise Policy Q&A Bot", "t", "middle")
for i, line in enumerate(("answers questions about ACME's HR, technical",
                          "and compliance manuals, listing the source files",
                          "Python · LangGraph · Streamlit")):
    text(780, 230 + 18 * i, line, "s", "middle")
person(150, 120, "Employee", "asks policy questions")
person(150, 360, "Developer", "loads documents, runs tests")
box(600, 30, 360, 80, "docs/ · part of this repo", [
    "3 ACME manuals: hr · technical · compliance",
    "plain text, read once at ingestion"], cls="dt")
box(1200, 50, 320, 96, "Pinecone · vector database", [
    "the bot's own index (D2 in figure 3)",
    "55 chunks as vectors + text · AWS us-east-1"], cls="pc")
box(1200, 196, 320, 96, "LLM API · Groq or OpenAI", [
    "llama-3.3-70b-versatile or gpt-4o-mini",
    "routes, grades, answers and checks"], cls="ex")
box(1200, 342, 320, 96, "Hugging Face Hub", [
    "hosts the all-MiniLM-L6-v2 model",
    "the bot downloads it on first use"], cls="ex")
fl("M198 200 H598", P)
label(398, 192, "a question, typed in the chat", anchor="middle")
fl("M598 240 H198", P)
label(398, 257, "the answer + the source file names", anchor="middle")
fl("M198 440 H780 V332", P)
label(400, 432, "loads the documents, runs the 15-question test, sets the API keys", anchor="middle")
fl("M860 332 V478 H205", P)
label(430, 494, "test results: console summary + evaluation_report.json", anchor="middle")
fl("M780 110 V168", P)
label(790, 145, "read once, at ingestion")
fl("M920 168 V120 H1198", P)
label(1080, 112, "upsert chunks · search", anchor="middle")
fl("M1198 140 H940 V166", P)
label(1080, 154, "matching chunks", anchor="middle")
fl("M960 252 H1198", P)
label(1080, 244, "prompts (~7 a question)", anchor="middle")
fl("M1198 276 H962", P)
label(1080, 293, "replies", anchor="middle")
fl("M1198 390 H1100 V310 H962", P)
label(1092, 360, "model weights, first run", anchor="end")
svg_ctx, H_CTX = "\n".join(out), 510

# ================================================================ 3 · data flow (level 1)
out = []
P = "df"
ent(560, 52, 900, 70, "E3", "LLM provider: Groq API or OpenAI API",
    "llama-3.3-70b-versatile (default) or gpt-4o-mini · temperature 0")
CH = [560 + i * 192.5 for i in range(5)]
procs = [("P2", "Route", ("router node", "1 LLM call")),
         ("P3", "Retrieve", ("retriever node", "no LLM call")),
         ("P4", "Grade", ("grader node", "1 LLM call a chunk")),
         ("P5", "Answer", ("generator node", "1 LLM call")),
         ("P6", "Check", ("checker node", "0 or 1 LLM call"))]
for x, (pid, t, ls) in zip(CH, procs):
    proc(x, 280, 130, 92, pid, t, ls)
for i in range(4):
    fl(f"M{CH[i] + 130} 326 H{CH[i + 1] - 2}", P)
for i, lines in enumerate((("question", "+ doc_type"), ("question,", "4 or 6", "chunks"),
                           ("question +", "kept chunks"), ("answer +", "kept chunks"))):
    mid = CH[i] + 130 + 31
    for j, line in enumerate(lines):
        text(mid, 317 - 13 * (len(lines) - 1 - j), line, "lbs", "middle")
LLM_LABELS = {0: ("router prompt", "+ question", "↓ one word"),
              2: ("grader prompt", "+ question, chunk", "↓ yes or no, each"),
              3: ("rules + chunks", "+ question", "↓ the answer"),
              4: ("checker prompt", "+ chunks + answer", "↓ yes or no")}
for i, ls in LLM_LABELS.items():
    x = CH[i]
    fl(f"M{x + 16} 278 V124", P)
    fl(f"M{x + 114} 124 V278", P)
    for j, line in enumerate(ls):
        text(x + 65, 178 + 15 * j, line, "lbs", "middle")
out.append(f'<path d="M{CH[2] + 30} 374 Q{(CH[1] + CH[2] + 130) / 2} 428 {CH[1] + 100} 376" class="lnc" '
           f'marker-end="url(#{P}arc)"/>')
text(945, 452, "retry: question + doc_type 'general'", "lblc", "middle")
out.append(f'<path d="M{CH[4] + 30} 374 Q{(CH[3] + CH[4] + 130) / 2} 428 {CH[3] + 100} 376" class="lnc" '
           f'marker-end="url(#{P}arc)"/>')
text((CH[3] + CH[4] + 130) / 2, 440, "regenerate: same chunks + question", "lblc", "middle")
fl(f"M{CH[4] + 130} 326 H{CH[4] + 160}", P)
out.append(f'<circle cx="{CH[4] + 172}" cy="326" r="12" class="cn"/>')
text(CH[4] + 172, 330.5, "R", "cnt", "middle")
text(CH[4] + 172, 354, "final state", "lbs", "middle")
text(CH[4] + 172, 367, "to caller", "lbs", "middle")
# employee side
ent(30, 285, 160, 60, "E1", "Employee", "in a browser")
proc(258, 270, 150, 100, "P7", "Present", ("app.py · Streamlit", "chat, sources,", "namespace, retries"))
fl("M190 300 H256", P)
text(223, 293, "question", "lbs", "middle")
fl("M256 336 H192", P)
text(223, 351, "answer +", "lbs", "middle")
text(223, 364, "sources", "lbs", "middle")
fl("M408 305 H558", P)
text(483, 297, "question", "lbs", "middle")
out.append('<circle cx="333" cy="240" r="12" class="cn"/>')
text(333, 244.5, "R", "cnt", "middle")
fl("M333 252 V268", P)
store(250, 410, 220, 46, "D4", "Chat history", ("st.session_state",))
fl("M310 370 V408", P)
fl("M370 408 V372", P)
text(302, 395, "messages", "lbs", "end")
text(378, 395, "history", "lbs")
# evaluation side
ent(30, 494, 160, 60, "E2", "Developer", "runs the scripts")
proc(258, 490, 150, 92, "P8", "Evaluate", ("evaluate.py", "15 questions"))
fl("M190 522 H256", P)
text(223, 515, "command", "lbs", "middle")
fl("M256 546 H192", P)
text(223, 562, "console:", "lbs", "middle")
text(223, 575, "lines + x/15", "lbs", "middle")
fl("M408 520 H500 V346 H558", P)
text(492, 470, "15 questions", "lbs", "end")
out.append('<circle cx="450" cy="600" r="12" class="cn"/>')
text(450, 604.5, "R", "cnt", "middle")
fl("M438 600 H410 V584", P)
store(250, 622, 260, 46, "D5", "evaluation_report.json", ("summary + 15 results",))
fl("M333 582 V620", P)
text(325, 600, "summary +", "lbs", "end")
text(325, 613, "15 rows", "lbs", "end")
# Pinecone, the model cache, ingestion
store(790, 470, 280, 46, "D2", "Pinecone index · 3 namespaces", ("vector + text + {doc_type, source}",))
fl(f"M{CH[1] + 90} 468 V374", P)
text(CH[1] + 82, 455, "4 or 6 chunks", "lbs", "end")
store(520, 470, 170, 46, "D6", "Model cache", ("MiniLM weights",))
fl("M690 486 H768 V374", P)
text(729, 480, "weights", "lbs", "middle")
proc(720, 590, 260, 80, "P1", "Ingest documents", ("load · chunk 512/64 · embed · upsert",))
fl("M900 588 V518", P)
text(908, 560, "55 chunks: vectors + text + metadata", "lbs")
fl("M720 606 H660 V518", P)
text(668, 552, "cached", "lbs")
text(668, 565, "weights", "lbs")
fl("M580 518 V640 H718", P)
text(572, 600, "weights", "lbs", "end")
store(540, 690, 150, 46, "D1", "docs/", ("3 .txt manuals",))
fl("M690 713 H760 V672", P)
text(725, 706, "3 manuals", "lbs", "middle")
ent(1080, 600, 180, 56, "E4", "Hugging Face Hub")
fl("M1080 628 H982", P)
text(1031, 620, "MiniLM weights", "lbs", "middle")
text(1031, 643, "(first use)", "lbs", "middle")
ent(820, 712, 160, 44, "E2", "Developer", dup=True)
fl("M900 712 V672", P)
text(908, 696, "command", "lbs")
store(30, 160, 230, 60, "D3", ".env + config.py", ("keys, provider, k, retries",
                                                     "read by P1–P8 (not drawn)"))
svg_dfd, H_DFD = "\n".join(out), 780

# ================================================================ 4 · data model
out = []
P = "dm"
CW4, G4 = 280, 27
xs = [14 + i * (CW4 + G4) for i in range(5)]
hs = [
    card(xs[0], 40, CW4, "1 · Source file", [
        ("format", "plain text, UTF-8"),
        ("size", "5.8 / 6.5 / 7.6 KB"),
        ("layout", "numbered sections, e.g."),
        ("", "'4. REMOTE WORK POLICY'"),
        ("where", "docs/<folder>/<file>.txt")], 66, sub="one file per folder", cls="dt"),
    card(xs[1], 40, CW4, "2 · Document", [
        ("page_content", "the whole file"),
        ("metadata", ""),
        ("  .source", "'hr_policy.txt'"),
        ("  .doc_type", "'hr' (the folder)")], 112, sub="TextLoader, then 2 labels set"),
    card(xs[2], 40, CW4, "3 · Chunk (Document)", [
        ("page_content", "≤ 512 characters"),
        ("metadata", "same source, doc_type")], 112, sub="splitter 512 / 64 · 55 chunks in all"),
    card(xs[3], 40, CW4, "4 · Pinecone record", [
        ("id", "random uuid4 string"),
        ("values", "float[384], normalized"),
        ("metadata.text", "the chunk text"),
        ("metadata.source", "file name"),
        ("metadata.doc_type", "folder name"),
        ("namespace", "hr | technical | compliance")], 128, sub="index 'enterprise-rag', cosine", cls="pc"),
    card(xs[4], 40, CW4, "5 · Retrieved chunk", [
        ("id", "the record id"),
        ("page_content", "metadata.text, popped"),
        ("metadata", "{source, doc_type}"),
        ("score", "not kept")], 112, sub="similarity_search, k 4 or 2 × 3"),
]
for i in range(4):
    fl(f"M{xs[i] + CW4} 92 H{xs[i + 1] - 2}", P)
y2 = 40 + max(hs) + 40
h6 = card(14, y2, 500, "6 · RAGState · src/state.py (TypedDict)", [
    ("question", "str · set once by run_query"),
    ("doc_type", "str · 'hr' | 'technical' | 'compliance' | 'general'"),
    ("documents", "List[Document] · retrieved, then the kept ones"),
    ("generation", "str · the answer"),
    ("grading_result", "str · 'relevant' | 'not_relevant'"),
    ("hallucination_result", "str · 'grounded' | 'not_grounded'"),
    ("retry_count", "int · starts at 0; ends at 1–3 (checker +1 a pass)")], 168,
    sub="passed to every node; each returns {**state, …}", cls="st")
h7 = card(544, y2, 480, "7 · LLM replies, as parsed", [
    ("router", "text → strip, lowercase, strip quotes;"),
    ("", "not hr|technical|compliance|general → 'general'"),
    ("grader", "JSON {\"score\": \"yes\" | \"no\"}; missing → 'no';"),
    ("", "any error (bad JSON or a failed call) → kept"),
    ("generator", "plain text (StrOutputParser), may be Markdown"),
    ("checker", "JSON {\"score\": \"yes\" | \"no\"}; missing → 'yes';"),
    ("", "any error (bad JSON or a failed call) → 'grounded'")], 92,
    sub="each node turns its reply into a state field")
h8 = card(1054, y2, 492, "8 · Chat message · st.session_state.messages", [
    ("user", "{role: 'user', content}"),
    ("assistant", "{role: 'assistant', content, sources,"),
    ("", " doc_type, retry_count}"),
    ("sources", "sorted unique file names of the kept chunks"),
    ("error", "{role: 'assistant', content: 'Pipeline error: …'}")], 92,
    sub="kept for the browser session; never sent to the graph")
y3 = y2 + max(h6, h7, h8) + 32
h9 = card(14, y3, 500, "9 · Test question · evaluate.py EVAL_QUESTIONS", [
    ("id", "int · 1 to 15"),
    ("category", "str · HR, Technical, Compliance, Edge Case — …"),
    ("question", "str"),
    ("expected_namespace", "str · 'general' for Q11–Q14"),
    ("expected_answerable", "bool · False for Q12 and Q15"),
    ("note", "str · what the question tests")], 168,
    sub="15 items in code; expected answers only in the doc")
h10 = card(544, y3, 480, "10 · evaluation_report.json", [
    ("summary", "{llm_provider, total_questions: 15,"),
    ("", " routing_accuracy: 'x/15', answerability_pass: 'x/15'}"),
    ("results[]", "{id, category, question, note, expected_namespace,"),
    ("", " actual_namespace, routing_correct, expected_answerable,"),
    ("", " answerability_pass, docs_retrieved (= chunks kept),"),
    ("", " sources, grading_result, hallucination_result,"),
    ("", " retry_count, latency_seconds, answer}"),
    ("on error", "{id, question, error}")], 92, sub="written at the end of a run; gitignored")
h11 = card(1054, y3, 492, "11 · Settings · .env and src/config.py", [
    ("LLM_PROVIDER", "'groq' (default); any other value → OpenAI"),
    ("*_API_KEY", "GROQ, OPENAI, PINECONE"),
    ("PINECONE_INDEX_NAME", "'enterprise-rag'"),
    ("PINECONE_DIMENSION", "384"),
    ("TOP_K_PER_NAMESPACE", "4 · TOP_K_GENERAL 2"),
    ("MAX_RETRIES", "2")], 168, sub="read once at import (load_dotenv)", cls="cf")
y4 = y3 + max(h9, h10, h11) + 26
out.append(f'<rect x="14" y="{y4}" width="1532" height="104" rx="9" class="ct"/>')
text(28, y4 + 22, "How the structures turn into each other", "t2")
for j, line in enumerate((
        "5 → 6  retrieved chunks become state.documents; the grader replaces them with the 'yes' chunks",
        "7 → 6  the router's word → doc_type · grades → documents + grading_result · answer → generation · "
        "check → hallucination_result",
        "6 → 8  content = generation ('I couldn't generate an answer. The question may be out of scope.' if empty) · "
        "sources = sorted unique file names · doc_type ('unknown' if missing) · retry_count",
        "6 + 9 → 10  actual_namespace = doc_type · docs_retrieved = number of kept chunks · sources = a plain "
        "list ('?' if missing), not de-duplicated")):
    text(28, y4 + 42 + 16 * j, line, "m")
svg_dm, H_DM = "\n".join(out), int(y4 + 104 + 20)

# ================================================================ 6 · sequence, one question
out = []
P = "sq"
LIFE = [("Employee", "in a browser", 100), ("Streamlit", "app.py", 330), ("LangGraph", "graph nodes", 600),
        ("MiniLM", "local CPU", 860), ("Pinecone", "cloud", 1100), ("LLM API", "Groq or OpenAI", 1360)]
SEQ_END = 1290
for name, sub, x in LIFE:
    out.append(f'<rect x="{x - 80}" y="24" width="160" height="50" rx="8" class="ep"/>')
    text(x, 46, name, "t2", "middle")
    text(x, 63, sub, "m", "middle")
    out.append(f'<path d="M{x} 74 V{SEQ_END}" class="life"/>')
out.append(f'<rect x="324" y="116" width="12" height="{SEQ_END - 38 - 116}" class="act"/>')
out.append(f'<rect x="594" y="156" width="12" height="{SEQ_END - 76 - 156}" class="act"/>')
X = {n: x for n, _, x in LIFE}


def msg(a, b, y, s, ret=False, n=None):
    x1, x2 = X[a] + (6 if X[b] > X[a] else -6), X[b] + (-6 if X[b] > X[a] else 6)
    fl(f"M{x1} {y} H{x2}", P, "ret" if ret else "ln")
    text((x1 + x2) / 2, y - 7, s, "msg" if not ret else "lbl", "middle")
    fits(s, abs(x2 - x1) + 60, "s", "sequence")
    if n:
        out.append(f'<rect x="{X["LLM API"] + 20}" y="{y - 13}" width="{14 + 6.6 * len(n)}" height="19" '
                   f'rx="9.5" class="llm"/>')
        text(X["LLM API"] + 27 + 3.3 * len(n), y + 1, n, "llmt", "middle")


def frame(y1, y2, x1, x2, tab, tabw=180):
    out.append(f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" rx="6" class="frame"/>')
    out.append(f'<path d="M{x1} {y1} H{x1 + tabw} V{y1 + 14} L{x1 + tabw - 10} {y1 + 22} H{x1} Z" class="frtab"/>')
    text(x1 + 8, y1 + 15, tab, "frt")


def self_msg(y, s):
    x = X["LangGraph"] + 6
    out.append(f'<path d="M{x} {y} H{x + 40} V{y + 16} H{x + 2}" class="ln" marker-end="url(#{P}ar)"/>')
    text(x + 48, y + 12, s, "msg")


msg("Employee", "Streamlit", 116, "types a question in st.chat_input")
msg("Streamlit", "LangGraph", 156, "run_query(question)")
msg("LangGraph", "LLM API", 206, "router: system prompt + 'Question: …'", n="1")
msg("LLM API", "LangGraph", 238, "'hr'", ret=True)
msg("LangGraph", "MiniLM", 286, "load model; embed_query(question)")
msg("MiniLM", "LangGraph", 318, "384 numbers", ret=True)
msg("LangGraph", "Pinecone", 366, "query(namespace 'hr', top_k 4, include_metadata)")
msg("Pinecone", "LangGraph", 398, "4 matches: text + {doc_type, source}", ret=True)
frame(424, 520, 560, 1440, "loop [4 chunks]", 150)
msg("LangGraph", "LLM API", 468, "grader: rules + question + chunk (≤ 1,500 chars)", n="2–5")
msg("LLM API", "LangGraph", 500, "{\"score\": \"yes\"}", ret=True)
frame(536, 790, 560, 1440, "loop [none kept and retry_count < 2] · 0–2 times", 330)
self_msg(568, "retry_retrieve: doc_type 'general', retry_count + 1")
frame(600, 718, 580, 1180, "loop [3 namespaces]", 170)
msg("LangGraph", "MiniLM", 648, "load model; embed_query")
msg("MiniLM", "LangGraph", 668, "vector", ret=True)
msg("LangGraph", "Pinecone", 692, "query(namespace, top_k 2)")
msg("Pinecone", "LangGraph", 710, "2 matches", ret=True)
msg("LangGraph", "LLM API", 748, "grader × 6, as above", n="+6")
msg("LLM API", "LangGraph", 774, "{\"score\": …} × 6", ret=True)
msg("LangGraph", "LLM API", 822, "generator: rules + kept chunks (context) + 'Question: …'", n="6")
msg("LLM API", "LangGraph", 854, "the answer, plain text", ret=True)
frame(874, 1000, 560, 1440, "alt [chunks kept and retry_count < 2]", 280)
msg("LangGraph", "LLM API", 914, "checker: chunks (≤ 800 chars each) + the answer", n="7")
msg("LLM API", "LangGraph", 942, "{\"score\": \"yes\"}", ret=True)
out.append('<path d="M560 958 H1440" class="altsep"/>')
text(612, 976, "[else]", "frt")
text(716, 984, "no LLM call: hallucination_result = 'grounded'", "m")
self_msg(1012, "checker: retry_count + 1 (= 1 if no retry ran)")
frame(1046, 1192, 560, 1440, "opt [not grounded and retry_count < 2]", 270)
msg("LangGraph", "LLM API", 1086, "generator again: same prompt, same chunks", n="+1")
msg("LLM API", "LangGraph", 1108, "an answer", ret=True)
msg("LangGraph", "LLM API", 1132, "checker again: chunks + the answer", n="+1")
msg("LLM API", "LangGraph", 1154, "{\"score\": …}", ret=True)
self_msg(1162, "checker: retry_count = 2")
msg("LangGraph", "Streamlit", 1214, "the final RAGState", ret=True)
msg("Streamlit", "Employee", 1252, "answer, sources, namespace, Retries", ret=True)
text(215, 1270, "Retries = retry_count: 1 unless the", "lbs", "middle")
text(215, 1283, "retry loop or the opt ran", "lbs", "middle")
text(1470, SEQ_END + 18, "solid arrow: a call · dashed, open arrow: its reply · numbers: LLM calls", "m", "end")
svg_seq, H_SEQ = "\n".join(out), SEQ_END + 34

# ================================================================ 7 · context assembly (what each LLM call sees)
out = []
P = "pa"
COLS = [
    ("Router · route_question", "router.py", "once",
     ["You are an expert at routing user questions",
      "to the correct enterprise document category.",
      "hr: leave policy, benefits, performance reviews,",
      "  remote work, onboarding, code of conduct,",
      "  salary, disciplinary",
      "technical: APIs, authentication, rate limits,",
      "  error codes, deployments, system architecture,",
      "  SDKs, webhooks",
      "compliance: GDPR, data privacy, data retention,",
      "  incident response, vendor management, audits,",
      "  security policy, acceptable use",
      "general: spans categories, unclear, or none",
      "Respond with ONLY the single lowercase",
      "category name."],
     ["Question: {question}"],
     ["text → strip, lowercase, strip quotes",
      "anything else → 'general'"]),
    ("Grader · grade_documents", "grader.py", "per chunk: 4 or 6, plus 6 a retry",
     ["You are a relevance grader. Assess whether a",
      "retrieved document is relevant to a user question.",
      "Relevant if it contains keywords, facts, or",
      "semantic meaning that could help answer it.",
      "Be generous — partial relevance counts.",
      "Respond with JSON only:",
      "{\"score\": \"yes\"} or {\"score\": \"no\"}"],
     ["Question: {question}", "", "Document:", "{chunk text, first 1,500 chars}"],
     ["JsonOutputParser → score, 'no' if missing",
      "any error (bad JSON or a failed call) → kept"]),
    ("Generator · generate_answer", "generator.py", "once, again on a regenerate",
     ["You are an enterprise knowledge assistant for",
      "ACME Corporation. Answer using ONLY the",
      "information in the provided context documents.",
      "1. Strictly the context; no prior knowledge.",
      "2. Not enough context → say: \"I couldn't find a",
      "   definitive answer in the knowledge base. …\"",
      "3. Do NOT mention filenames or document names.",
      "4. Concise, professional and factual.",
      "5. Do NOT make up numbers, dates or policies.",
      "Context:",
      "{kept chunk texts, joined by '\\n\\n---\\n\\n'}",
      "  (none → 'No relevant documents were retrieved.')"],
     ["Question: {question}"],
     ["StrOutputParser → generation, plain text"]),
    ("Checker · check_hallucination", "checker.py", "after every answer, unless skipped",
     ["You are a hallucination detector. Determine",
      "whether an AI-generated answer is fully",
      "supported by the provided source documents.",
      "\"yes\" → ONLY information in the documents.",
      "\"no\" → facts, numbers or claims NOT found.",
      "Respond with JSON only:",
      "{\"score\": \"yes\"} or {\"score\": \"no\"}"],
     ["Source Documents:", "{each chunk, first 800 chars, joined by '\\n\\n'}", "",
      "Generated Answer:", "{generation}"],
     ["JsonOutputParser → score, 'yes' if missing",
      "any error (bad JSON or a failed call) → 'grounded'"]),
]
CW7, G7 = 366, 24
bottoms = []
for i, (title, f, times, sysl, huml, repl) in enumerate(COLS):
    x = 14 + i * (CW7 + G7)
    out.append(f'<rect x="{x}" y="30" width="{CW7}" height="56" rx="9" class="nd"/>')
    text(x + 12, 52, title, "t2")
    text(x + 12, 72, f"{f} · runs {times}", "m")
    y = 100
    hs_ = 30 + 15 * len(sysl)
    out.append(f'<rect x="{x}" y="{y}" width="{CW7}" height="{hs_}" rx="8" class="sysb"/>')
    text(x + 12, y + 19, "SYSTEM message (abridged)", "rl")
    for j, line in enumerate(sysl):
        text(x + 12, y + 37 + 15 * j, line, "pm")
        fits(line, CW7 - 20, "m", title)
    y += hs_ + 12
    hh = 30 + 15 * len(huml)
    out.append(f'<rect x="{x}" y="{y}" width="{CW7}" height="{hh}" rx="8" class="humb"/>')
    text(x + 12, y + 19, "HUMAN message", "rl")
    for j, line in enumerate(huml):
        text(x + 12, y + 37 + 15 * j, line, "pm")
        fits(line, CW7 - 20, "m", title)
    y += hh + 12
    fl(f"M{x + CW7 / 2} {y - 10} V{y + 6}", P)
    hr_ = 30 + 15 * len(repl)
    out.append(f'<rect x="{x}" y="{y + 8}" width="{CW7}" height="{hr_}" rx="8" class="repb"/>')
    text(x + 12, y + 27, "REPLY → state", "rl")
    for j, line in enumerate(repl):
        text(x + 12, y + 45 + 15 * j, line, "m")
        fits(line, CW7 - 20, "m", title)
    if i == 2:
        out.append(f'<circle cx="{x + CW7 - 16}" cy="{100 + 37 + 15 * 10 - 4}" r="9.5" class="wb"/>')
        text(x + CW7 - 16, 100 + 37 + 15 * 10, "!", "wbt", "middle")
    if i == 3:
        yh = 100 + hs_ + 12
        out.append(f'<circle cx="{x + CW7 - 16}" cy="{yh + 16}" r="9.5" class="wb"/>')
        text(x + CW7 - 16, yh + 20, "!", "wbt", "middle")
    bottoms.append(y + 8 + hr_)
YB = max(bottoms) + 28
out.append(f'<rect x="14" y="{YB}" width="1532" height="78" rx="9" class="ct"/>')
text(28, YB + 22, "Every call", "t2")
text(28, YB + 42, "chain = prompt | get_llm(temperature=0) [| parser] · a new client per node run (the grader reuses one for all its chunks) · "
     "no max_tokens, no timeout, no retry set", "s")
text(28, YB + 62, "never sent: the chat history, earlier answers, file names (the generator's context has chunk text only)"
     " · ! the chunks sit in the generator's SYSTEM message, and the checker never sees the question", "s")
svg_pa, H_PA = "\n".join(out), YB + 96

# ================================================================ 8 · threat model
out = []
P = "tm"
TM_BOTTOM = 760
out.append(f'<rect x="226" y="40" width="486" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(242, 62, "TB2 · your machine", "tbt")
out.append(f'<rect x="760" y="40" width="244" height="{TM_BOTTOM - 40}" rx="12" class="tb"/>')
text(776, 62, "TB3 · third-party cloud", "tbt")
out.append('<path d="M206 40 V400" class="tbl"/>')
text(200, 56, "TB1", "tbt", "end")
text(200, 72, "browser", "lbs", "end")
person(70, 120, "Employee", "any browser")
person(110, 470, "Developer", "works locally")


def tbox(x, y, w, h, title, lines, threats, cls="bx"):
    box(x, y, w, h, title, lines, cls=cls)
    for k, t in enumerate(threats):
        cx, cy = x + w - 20 - 34 * k, y + h - 14
        out.append(f'<rect x="{cx - 16}" y="{cy - 9}" width="32" height="18" rx="9" class="wb"/>')
        text(cx, cy + 4, t, "wbt", "middle")


tbox(246, 90, 200, 110, "Streamlit app", ["app.py, port 8501", "no login · Markdown",
                                           "output · raw errors"], ["T11", "T10", "T1"], cls="ep")
tbox(486, 90, 206, 170, "LangGraph pipeline", ["router · retriever · grader", "generator · checker",
                                                 "question and chunk text", "go into the prompts"],
     ["T6", "T3", "T2"], cls="nd")
tbox(246, 230, 200, 70, ".env", ["3 API keys on disk"], ["T5"], cls="cf")
tbox(246, 330, 200, 76, "docs/", ["3 policy manuals"], ["T3"], cls="dt")
tbox(486, 300, 206, 110, "Ingestion job", ["src/ingestion.py", "random ids, no checksums"], ["T7"])
tbox(246, 446, 200, 84, "Console + session", ["print() logs,", "chat in session_state"], ["T8"])
tbox(486, 446, 206, 84, "Embedding model", ["MiniLM, cached locally"], ["T9"])
tbox(780, 90, 204, 110, "LLM API", ["Groq or OpenAI", "gets questions + chunks"], ["T4"], cls="ex")
tbox(780, 240, 204, 110, "Pinecone", ["stores chunk text", "AWS us-east-1"], ["T7", "T4"], cls="ex")
tbox(780, 446, 204, 84, "Hugging Face Hub", ["model, no pinned revision"], ["T9"], cls="ex")
fl("M110 130 H244", P)
text(200, 122, "question", "lbs", "end")
fl("M244 168 H110", P)
text(200, 184, "answer (Markdown),", "lbs", "end")
text(200, 197, "sources, errors", "lbs", "end")
fl("M446 138 H484", P)
fl("M692 130 H778", P, "lnr")
text(736, 122, "prompts", "lbs", "middle")
fl("M778 172 H694", P, "lnr")
text(736, 165, "replies", "lbs", "middle")
fl("M650 262 V300 H778", P, "lnr")
text(736, 294, "search", "lbs", "middle")
fl("M778 252 H694", P, "lnr")
text(736, 246, "chunks", "lbs", "middle")
fl("M446 368 H484", P)
fl("M692 380 H778", P, "lnr")
text(736, 372, "upsert", "lbs", "middle")
fl("M446 262 H468 V200 H484", P, "lnd")
text(452, 250, "keys", "lbs")
fl("M150 500 H230 V380 H244", P)
text(226, 520, "edits docs/,", "lbs", "end")
text(226, 533, "runs scripts", "lbs", "end")
fl("M780 488 H694", P, "lnr")
text(736, 480, "weights", "lbs", "middle")
out.append('<rect x="250" y="566" width="442" height="60" rx="8" class="nt"/>')
text(262, 586, "Trust boundaries: TB1 browser → app · TB2 your machine · TB3 cloud", "m")
text(262, 603, "Red arrows: data crossing TB3, to or from the cloud · untrusted text", "m")
text(262, 620, "from docs/ and from the question ends up inside LLM prompts (T2, T3)", "m")
THREATS = [
    ("T1", "Spoofing · no login on the app",
     "Anyone who can reach port 8501 can ask about every",
     "namespace; there are no users or permissions.", "today: none"),
    ("T2", "Tampering · direct prompt injection",
     "The question goes unfiltered into the router, grader",
     "and generator prompts.", "today: none"),
    ("T3", "Tampering · indirect prompt injection",
     "Document text sits in the generator's SYSTEM message and in the",
     "grader and checker prompts: it can steer answers and force 'yes'.", "today: none"),
    ("T4", "Information disclosure · third parties",
     "Questions and chunk text go to Groq or OpenAI; full",
     "chunk text is stored in Pinecone's cloud.", "today: none (each provider's retention terms apply)"),
    ("T5", "Information disclosure · secrets",
     "3 API keys sit in .env on disk (gitignored) and are",
     "read into the clients; no secret store or rotation.", "today: .gitignore only"),
    ("T6", "Denial of service · cost",
     "Up to 20 LLM calls a question, no rate limit, no timeout",
     "or max_tokens set in code: one user can run up the bill.", "today: MAX_RETRIES 2 only"),
    ("T7", "Tampering · index integrity",
     "Re-running ingestion appends copies; anyone with the",
     "Pinecone key can write; no checksums of documents.", "today: none"),
    ("T8", "Repudiation · no audit trail",
     "Only print() to the console; chats live in the",
     "session; no record of who asked what.", "today: none"),
    ("T9", "Tampering · supply chain",
     "requirements.txt pins nothing; the model is pulled",
     "from the Hub without a pinned revision.", "today: none"),
    ("T10", "Tampering · output handling",
     "The answer is rendered as Markdown (st.write): links or",
     "images from the model or from docs/ show in the browser.", "today: HTML is escaped, Markdown is not"),
    ("T11", "Information disclosure · error text",
     "st.error shows the raw exception text to anyone who",
     "can reach the app.", "today: none"),
]
out.append(f'<rect x="1024" y="40" width="522" height="{TM_BOTTOM - 40}" rx="12" class="nt"/>')
text(1040, 64, "Threats (STRIDE) and what the code does today", "t2")
for i, (tid, head, l1, l2, today) in enumerate(THREATS):
    y = 92 + i * 61
    out.append(f'<rect x="1036" y="{y - 13}" width="34" height="18" rx="9" class="wb"/>')
    text(1053, y, tid, "wbt", "middle")
    text(1078, y, head, "t3")
    text(1078, y + 15, l1, "m")
    text(1078, y + 29, l2, "m")
    text(1078, y + 43, today, "mi")
    for line in (head, l1, l2):
        fits(line, 460, "m", tid)
svg_tm, H_TM = "\n".join(out), TM_BOTTOM + 20

# ================================================================ 9 · evaluation pipeline
out = []
P = "ev"
box(14, 40, 300, 176, "EVAL_QUESTIONS · 15", [
    "HR 4 · Technical 3 · Compliance 3",
    "Edge cases 5: cross-document 2,",
    "out of scope, ambiguous, trap",
    "each: expected_namespace,",
    "expected_answerable, note",
    "evaluate.py:26-139"], cls="dt")
box(354, 40, 300, 176, "For each question, in order", [
    "start_time = time.time()",
    "result = run_query(question):",
    "the whole graph, ~7 LLM calls",
    "elapsed = round(time.time() - start_time, 2)",
    "an exception → {id, question, error},",
    "and the run goes on"], cls="nd")
box(694, 40, 420, 176, "Scoring", [
    "score_routing: expected 'general' → pass;",
    "  otherwise pass if actual == expected",
    "score_answerability: answerable → pass,",
    "  whatever the answer says; unanswerable →",
    "  pass if the answer has one of 9 phrases:",
    "  'couldn't find', 'not covered', 'not available',",
    "  'no information', 'out of scope', 'knowledge base',",
    "  'don't have', 'cannot find', 'unable to find'"], cls="ep", step=15)
box(1154, 40, 392, 82, "Console", [
    "per question: route, chunks kept, grading,",
    "check, retries, latency, first 120 chars",
    "summary: routing x/15 · answerability x/15"], cls="ex", step=15)
box(1154, 136, 392, 80, "evaluation_report.json", [
    "summary + 15 result rows (see the data model)",
    "written at the end · gitignored"], cls="pc")
fl("M314 128 H352", P)
fl("M654 128 H692", P)
fl("M1114 90 H1152", P)
fl("M1114 176 H1152", P)
box(14, 254, 640, 112, "In the solution doc only (not in code)", [
    "expected answers for Q1–Q15, e.g. Q1 '15 days; accrues 1.25 days/month …',",
    "Q9 '72 hours (GDPR Article 33)'; most questions are worded differently",
    "from evaluate.py (Q5 and Q13 match); nothing compares an answer with these"], cls="cf")
out.append('<path d="M164 254 V218" class="lnd"/>')
text(172, 240, "same 15 topics, mostly different wording", "lbs")
out.append('<rect x="694" y="254" width="852" height="128" rx="9" class="nt"/>')
text(708, 276, "Not measured", "t2")
for j, line in enumerate((
        "retrieval quality: no expected chunk or source, so no hit rate, precision or recall",
        "answer correctness against the expected answers · groundedness by an independent judge",
        "tokens and cost per question · repeat runs (temperature 0, but nothing pins the results)",
        "routing for the 4 'general' questions (Q11–Q14), and answers to the 13 answerable ones, always pass",
        "errors count as fails in x/15 (the summary doesn't separate them) · hallucination_result is recorded, not scored")):
    text(708, 296 + 17 * j, line, "m")
svg_ev, H_EV = "\n".join(out), 400

# ================================================================ 10 · the recommended architecture
out = []
P = "rc"
text(20, 28, "WHAT AN FDE WOULD BUILD · the number in a corner is the 2.5 decision that part answers", "h")
text(20, 54, "INGEST AND KEEP CURRENT", "rl")
box(20, 66, 200, 110, "Policy documents", ["HR, IT and compliance;", "owners and readers", "recorded"], cls="ex")
box(250, 66, 230, 110, "Scheduled sync", ["stable ids: file + chunk", "hash; delete-then-upsert", "per file"], cls="nd",
    tag="14")
box(510, 66, 230, 110, "Chunks with section titles", ["each chunk carries its", "section title and the",
                                                        "source's permissions"], cls="nd", tag="5, 17, 18")
box(770, 66, 220, 110, "Embed", ["model chosen on the", "golden set"], cls="nd", tag="6")
box(1020, 66, 260, 110, "Vector store", ["region or self-hosted to", "meet data residency;", "reader groups on chunks"],
    cls="dt", tag="7, 18")
for x in (222, 482, 742, 992):
    fl(f"M{x} 121 H{x + 26}", P)
box(1310, 66, 230, 110, "LLM vendor", ["approved vendor; test", "the model you ship"], cls="ex", tag="8")
text(20, 232, "ANSWER A QUESTION", "rl")
fl("M1100 178 V246 H790 V286", P)
label(945, 240, "chunks the asker may read", "middle")
fl("M1410 266 V180", P)
label(1402, 226, "prompts", "end")
fl("M1450 180 V266", P)
label(1458, 226, "replies")
person(50, 300, "Employee", "signed in")
box(90, 288, 170, 124, "Their channel", ["Teams, Slack or", "intranet; single", "sign-on; no debug",
                                         "metrics"], cls="nd", tag="13")
out.append('<rect x="282" y="268" width="1256" height="162" rx="14" class="bndc"/>')
text(300, 262, "Q&A SERVICE", "rl")
box(300, 288, 180, 124, "Rewrite follow-ups", ["standalone question", "from the chat history"], cls="nd",
    tag="16")
box(500, 288, 180, 124, "Route", ["multi-label, or", "search every family"], cls="nd", tag="3, 4")
box(700, 288, 180, 124, "Retrieve", ["only chunks the", "asker may read"], cls="nd", tag="18")
box(900, 288, 180, 124, "Filter chunks", ["an LLM grader, or a", "re-ranker if its 4–6", "calls cost too much"], cls="nd", tag="9")
box(1100, 288, 200, 124, "Generate", ["only from the context;", "cites the section;",
                                      "refuses with a next step"], cls="nd", tag="12, 17")
box(1320, 288, 200, 124, "Check", ["grounded, or quotes", "verified; else refuse", "or mark “not verified”"],
    cls="nd", tag="10, 11")
fl("M76 347 H88", P)
fl("M262 350 H298", P)
for x in (482, 682, 882, 1082, 1302):
    fl(f"M{x} 350 H{x + 16}", P)
fl("M1420 414 V458 H50 V406", P)
label(735, 452, "answer, with the section it came from", "middle")
box(20, 480, 1520, 74, "Golden set and failure causes", [
    "golden set signed off by the helpdesk and the document owners: expected behaviour, facts and section for each question; paraphrases, "
    "follow-ups, wrong premises, traps and restricted questions",
    "each run records every stage and scores retrieval hits, correctness, groundedness, refusals, latency and calls; "
    "three runs, a few questions held back; every failure gets one cause (2.7)"], cls="nt", tag="15")
text(20, 586, "THE ENGAGEMENT, STEPS 5–10 OF 2.8", "rl")
STAGES = [("5 · Thin slice", ["naive RAG (option A),", "then a baseline run"], None),
          ("6 · Fix, re-run, repeat", ["each added part for a", "measured failure"], "1"),
          ("7 · Findings readout", ["per-question results", "and a go/no-go"], None),
          ("8 · Security review", ["threat model and", "approvals confirmed"], None),
          ("9 · Pilot", ["a small group; unanswered", "questions logged"], None),
          ("10 · Handoff", ["runbook, owner, re-index", "and evaluation schedules"], None)]
for i, (t, ls, tg) in enumerate(STAGES):
    x = 20 + i * 256
    box(x, 598, 240, 82, t, ls, cls="nt", tag=tg)
    if i:
        fl(f"M{x - 16} 639 H{x - 2}", P)
svg_rc, H_RC = "\n".join(out), 700

OLD_DEFS = {
    "architecture": ('<defs><marker id="har" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                     'orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ah"/></marker><marker id="harc" '
                     'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                     '<path d="M0,0 L10,5 L0,10 z" class="ahc"/></marker></defs>'),
    "design": ('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
               'orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ah"/></marker><marker id="arc" '
               'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
               '<path d="M0,0 L10,5 L0,10 z" class="ahc"/></marker></defs>'),
}
FIGS = [
    ("context", "System context", "Before anything else: what the system is, who uses it, and what it depends on.",
     svg_ctx, 1560, H_CTX, defs("cx"),
     "System context: employees ask the Enterprise Policy Q&A Bot questions and get answers with source file names; "
     "a developer loads documents, runs tests and sets keys; the bot reads ACME's policy documents once and uses "
     "Pinecone, an LLM API (Groq or OpenAI) and the Hugging Face Hub."),
    ("architecture", "High-level architecture", "Then the parts and where they run: local Python or cloud APIs.",
     svg_high, HW, HH, OLD_DEFS["architecture"],
     "High-level architecture: a Streamlit chat UI and an evaluation script call the LangGraph pipeline, which uses a "
     "local MiniLM embedding model, Pinecone and an LLM API; an ingestion job fills Pinecone from docs/."),
    ("dataflow", "Data flow (level 1)", "Then what data moves between those parts, and where it is stored.",
     svg_dfd, 1560, H_DFD, defs("df"),
     "Level-1 data flow: the employee's question goes through Present, Route, Retrieve, Grade, Answer and Check; "
     "four of these exchange prompts and replies with the LLM provider; Retrieve reads the Pinecone store that "
     "Ingest fills from docs/; Evaluate sends 15 questions and writes evaluation_report.json."),
    ("datamodel", "Data model", "Then the exact shape of each piece of data in those flows.",
     svg_dm, 1560, H_DM, defs("dm"),
     "Data model: source file, Document, chunk, Pinecone record and retrieved chunk; RAGState; the parsed LLM replies; "
     "chat messages; the test questions, the evaluation report and the settings."),
    ("design", "Detailed design", "Then every file, function, setting and loop that implements them.",
     svg, W, H, OLD_DEFS["design"],
     "Detailed design: ingestion steps, the LangGraph nodes with their settings and loops, the entry points, "
     "RAGState, external services and numbered review notes."),
    ("sequence", "Sequence: one question", "Then one request through those parts, call by call, in time order.",
     svg_seq, 1560, H_SEQ, defs("sq"),
     "Sequence of one question: Streamlit calls run_query; the graph calls the LLM to route, loads MiniLM and embeds "
     "the question, queries Pinecone, grades each of 4 chunks with the LLM, generates and checks the answer, and "
     "returns the final state; the retry and regenerate branches are shown as frames."),
    ("prompts", "Context assembly", "Then what each of those LLM calls is sent (system prompts abridged; the full text is in src/nodes/*.py).",
     svg_pa, 1560, H_PA, defs("pa"),
     "Context assembly for the four LLM calls: the system and human messages of the router, grader, generator and "
     "checker, and how each reply is parsed into the state."),
    ("threats", "Threat model", "With all of that drawn: where it could be attacked, and what protects it today.",
     svg_tm, 1560, H_TM, defs("tm"),
     "Threat model: trust boundaries between the browser and the app, your machine, and the cloud; eleven STRIDE "
     "threats, from the missing login to raw error text, each marked on the part it affects."),
    ("evaluation", "Evaluation pipeline", "Then how the finished bot is tested, and what the test does not measure.",
     svg_ev, 1560, H_EV, defs("ev"),
     "Evaluation pipeline: 15 questions run one by one through run_query, scored for routing and answerability, "
     "printed and written to evaluation_report.json; retrieval quality and answer correctness are not measured."),
    ("recommended", "The recommended architecture", "Finally: the design an FDE would build, with the 2.5 decision each numbered part answers.",
     svg_rc, 1560, H_RC, defs("rc"),
     "The recommended architecture: policy documents synced on a schedule with stable ids into chunks that carry their section title and the source's permissions, embedded into a vector store in an approved region; questions arrive through the employee's own channel with single sign-on, are rewritten if they are follow-ups, routed to one or more families, retrieved within the asker's permissions, filtered, answered from the context with the section cited or refused with a next step, and checked, failing closed; a golden set with one cause per failure, and the engagement from a thin slice to handoff."),
]
FDE = Path(__file__).with_name("fde_2a.html").read_text(encoding="utf-8")
# Keep hyphenated terms on one line, then label every table cell with its column so phones can show rows as cards.
for tok in ("us-east-1", "fail-open", "Fail-open", "fail-closed", "in-house", "top-k", "top-4", "re-ranker",
            "delete-then-upsert", "gpt-4o-mini", "all-MiniLM-L6-v2", "go/no-go", "git-ignored", "512-character",
            "cross-encoder", "record-keeping", "re-run"):
    FDE = FDE.replace(tok, f'<span class="nw">{tok}</span>')


def card_table(m):
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th>(.*?)</th>", m.group(0), re.S)]

    def row(r):
        cols = iter(heads)
        return re.sub(r"<td>", lambda _: f'<td data-h="{escape(next(cols, ""))}">', r.group(0))
    return re.sub(r"<tr><td>.*?</tr>", row, m.group(0), flags=re.S)


FDE = re.sub(r'<table class="qt[^"]*">.*?</table>', card_table, FDE, flags=re.S)
FDE_NAV = [("fde-mindset", "2.1", "How an FDE reads a brief"), ("fde-brief", "2.2", "The brief, phrase by phrase"),
           ("fde-people", "2.3", "Who to talk to"), ("fde-questions", "2.4", "Questions to ask"),
           ("fde-decisions", "2.5", "Decision trace"), ("fde-assumptions", "2.6", "Hidden assumptions"),
           ("fde-stress", "2.7", "The stress test"), ("fde-plan", "2.8", "Engagement steps"),
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
  <p class="lede">Ten diagrams in the order a design is reasoned out: scope, parts, data, behaviour, risk and
    proof, then the design an FDE would build instead. Each answers a group of the discovery questions above (see 2.9).</p>
</section>"""
parts = []
for i, (a, t, why, body_svg, w, h, d, aria) in enumerate(FIGS, 1):
    parts.append(f"""<section id="{a}">
  <h2><span class="num">{i}</span>{escape(t)}</h2>
  <p class="cap"><span class="why">Why here:</span> {escape(why)}</p>
</section>
<figure>
  <div class="scroll">
  <svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(aria)}">
{d}
{body_svg}
  </svg>
  </div>
</figure>""")
body = FDE + "\n" + PART3 + "\n" + "\n".join(parts)

page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>2A: Brief to Architecture</title>
<style>
  :root {{
    --bg: #fbfaf7; --surface: #ffffff; --text: #1f2328; --muted: #5d6470; --border: #e3e0d8;
    --accent: #2f5fb3; --accent-soft: #e9f0fb; --good: #1d7a46; --good-soft: #e6f4ec;
    --warn: #9a5b00; --warn-soft: #fbf1e0; --bad: #b3261e; --bad-soft: #fbe9e7; --violet: #6a4bb3; --violet-soft: #f0ebfa;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #16181c; --surface: #1d2026; --text: #e7e9ee; --muted: #a2a9b5; --border: #2e333c;
      --accent: #8fb2f0; --accent-soft: #1f2a3d; --good: #6fcf97; --good-soft: #1b2e24;
      --warn: #f0b860; --warn-soft: #33291a; --bad: #f28b82; --bad-soft: #3a2220; --violet: #b9a3f0; --violet-soft: #272236;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #16181c; --surface: #1d2026; --text: #e7e9ee; --muted: #a2a9b5; --border: #2e333c;
    --accent: #8fb2f0; --accent-soft: #1f2a3d; --good: #6fcf97; --good-soft: #1b2e24;
    --warn: #f0b860; --warn-soft: #33291a; --bad: #f28b82; --bad-soft: #3a2220; --violet: #b9a3f0; --violet-soft: #272236;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.5 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
  header {{ max-width: 1560px; margin: 0 auto; padding: 28px 16px 8px; }}
  .eyebrow {{ color: var(--muted); font-size: 13px; letter-spacing: .06em; text-transform: uppercase; margin: 0 0 6px; }}
  h1 {{ font-size: 28px; line-height: 1.2; margin: 0 0 6px; }}
  .src {{ color: var(--muted); font-size: 14.5px; margin: 0; }}
  .src a {{ color: var(--accent); }}
  figure {{ max-width: 1560px; margin: 12px auto 32px; padding: 0 16px; }}
  .scroll {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); padding: 10px; }}
  svg {{ display: block; width: 100%; min-width: 1100px; height: auto; color: var(--text); }}
  svg text {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
  .t {{ font-size: 14.5px; font-weight: 650; fill: currentColor; }}
  .s {{ font-size: 12.5px; fill: var(--muted); }}
  .m {{ font-size: 12px; fill: var(--muted); }}
  .mf {{ font-size: 12px; font-weight: 650; fill: currentColor; font-family: Consolas, Menlo, monospace; }}
  .tag {{ font-size: 11px; fill: var(--muted); font-family: Consolas, Menlo, monospace; }}
  .h {{ font-size: 13.5px; font-weight: 750; letter-spacing: .07em; fill: currentColor; }}
  .hs {{ font-size: 12.5px; fill: var(--muted); }}
  .lbl {{ font-size: 12px; font-style: italic; fill: var(--muted); }}
  .lblc {{ font-size: 12px; font-style: italic; fill: var(--violet); }}
  .pt {{ font-size: 12.5px; font-weight: 600; fill: currentColor; }}
  .bx {{ fill: var(--bg); stroke: currentColor; stroke-opacity: .45; stroke-width: 1.2; }}
  .dt {{ fill: var(--warn-soft); stroke: var(--warn); stroke-opacity: .6; stroke-width: 1.2; }}
  .nd {{ fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.4; }}
  .lp {{ fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.3; stroke-dasharray: 5 4; }}
  .pc {{ fill: var(--good-soft); stroke: var(--good); stroke-width: 1.4; }}
  .cy {{ fill: var(--surface); stroke: var(--good); stroke-width: 1.3; }}
  .cyt {{ fill: var(--good-soft); stroke: var(--good); stroke-width: 1.3; }}
  .cf {{ fill: var(--bg); stroke: currentColor; stroke-opacity: .3; stroke-width: 1.1; stroke-dasharray: 3 3; }}
  .ep {{ fill: var(--bg); stroke: currentColor; stroke-opacity: .55; stroke-width: 1.3; }}
  .st {{ fill: var(--bg); stroke: var(--accent); stroke-opacity: .7; stroke-width: 1.2; }}
  .ex {{ fill: var(--bg); stroke: currentColor; stroke-opacity: .35; stroke-width: 1.1; }}
  .nt {{ fill: var(--warn-soft); stroke: var(--warn); stroke-opacity: .5; stroke-width: 1.1; }}
  .ct {{ fill: var(--bg); stroke: currentColor; stroke-opacity: .35; stroke-width: 1.1; }}
  .lg {{ fill: none; stroke: currentColor; stroke-opacity: .25; stroke-width: 1; }}
  .pl {{ fill: var(--surface); stroke: currentColor; stroke-opacity: .6; stroke-width: 1.3; }}
  .dm {{ fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.3; }}
  .dmt {{ font-size: 12px; font-weight: 650; fill: var(--violet); font-family: Consolas, Menlo, monospace; }}
  .llm {{ fill: var(--warn-soft); stroke: var(--warn); stroke-width: 1; }}
  .llmt {{ font-size: 11px; font-weight: 700; fill: var(--warn); }}
  .wb {{ fill: var(--bad-soft); stroke: var(--bad); stroke-width: 1.1; }}
  .wbt {{ font-size: 11px; font-weight: 700; fill: var(--bad); }}
  .dot {{ fill: var(--accent); }}
  .ln {{ fill: none; stroke: currentColor; stroke-opacity: .6; stroke-width: 1.5; }}
  .lnc {{ fill: none; stroke: var(--violet); stroke-width: 1.5; stroke-dasharray: 6 4; }}
  .ah {{ fill: currentColor; fill-opacity: .7; }}
  .ahc {{ fill: var(--violet); }}
  .bnd {{ fill: none; stroke: currentColor; stroke-opacity: .4; stroke-width: 1.3; stroke-dasharray: 8 5; }}
  .bndc {{ fill: var(--accent-soft); fill-opacity: .35; stroke: var(--accent); stroke-opacity: .6; stroke-width: 1.3;
    stroke-dasharray: 8 5; }}
  .pa {{ fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.3; }}
  .chip {{ fill: var(--surface); stroke: var(--accent); stroke-width: 1.2; }}
  .cht {{ font-size: 12.5px; font-weight: 650; fill: currentColor; }}
  .lnd {{ fill: none; stroke: currentColor; stroke-opacity: .5; stroke-width: 1.3; stroke-dasharray: 4 4; }}
  section {{ max-width: 1560px; margin: 0 auto; padding: 0 16px; }}
  h2 {{ font-size: 20px; margin: 22px 0 2px; }}
  h2 .num {{ color: var(--accent); margin-right: 6px; }}
  .cap {{ color: var(--muted); font-size: 14.5px; margin: 0; }}
  .t2 {{ font-size: 13.5px; font-weight: 650; fill: currentColor; }}
  .t3 {{ font-size: 12.5px; font-weight: 650; fill: currentColor; }}
  .mi {{ font-size: 11.5px; font-style: italic; fill: var(--good); }}
  .lbs {{ font-size: 11.5px; font-style: italic; fill: var(--muted); }}
  .msg {{ font-size: 12.5px; fill: currentColor; }}
  .pm {{ font-size: 12px; fill: currentColor; font-family: Consolas, Menlo, monospace; }}
  .rl {{ font-size: 11px; font-weight: 750; letter-spacing: .06em; fill: var(--muted); }}
  .pr {{ fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.4; }}
  .prl {{ stroke: var(--accent); stroke-opacity: .6; stroke-width: 1; fill: none; }}
  .pid {{ font-size: 11.5px; font-weight: 750; fill: var(--accent); }}
  .ee {{ fill: var(--surface); stroke: currentColor; stroke-opacity: .75; stroke-width: 1.8; }}
  .dupl {{ stroke: currentColor; stroke-opacity: .75; stroke-width: 1.5; }}
  .dsf {{ fill: var(--good-soft); }}
  .dsl {{ fill: none; stroke: var(--good); stroke-width: 1.5; }}
  .dsid {{ font-size: 12.5px; font-weight: 750; fill: var(--good); }}
  .cn {{ fill: var(--surface); stroke: var(--violet); stroke-width: 1.5; }}
  .cnt {{ font-size: 12px; font-weight: 750; fill: var(--violet); }}
  .life {{ fill: none; stroke: currentColor; stroke-opacity: .35; stroke-width: 1.2; stroke-dasharray: 5 5; }}
  .act {{ fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1; }}
  .frame {{ fill: none; stroke: currentColor; stroke-opacity: .4; stroke-width: 1.1; }}
  .frtab {{ fill: var(--bg); stroke: currentColor; stroke-opacity: .4; stroke-width: 1.1; }}
  .frt {{ font-size: 11.5px; font-weight: 700; fill: currentColor; }}
  .ret {{ fill: none; stroke: currentColor; stroke-opacity: .55; stroke-width: 1.3; stroke-dasharray: 5 4; }}
  .lnr {{ fill: none; stroke: var(--bad); stroke-width: 1.6; }}
  .ahr {{ fill: var(--bad); }}
  .tb {{ fill: none; stroke: var(--bad); stroke-opacity: .7; stroke-width: 1.6; stroke-dasharray: 9 5; }}
  .tbl {{ fill: none; stroke: var(--bad); stroke-opacity: .7; stroke-width: 1.6; stroke-dasharray: 9 5; }}
  .tbt {{ font-size: 12.5px; font-weight: 750; fill: var(--bad); }}
  .sysb {{ fill: var(--violet-soft); stroke: var(--violet); stroke-width: 1.1; }}
  .humb {{ fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.1; }}
  .repb {{ fill: var(--good-soft); stroke: var(--good); stroke-width: 1.1; }}
  nav {{ max-width: 1560px; margin: 14px auto 0; padding: 0 16px; }}
  nav .grp {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; margin: 0 0 10px; }}
  nav .gl {{ font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
    width: 200px; }}
  nav .pills {{ display: flex; flex-wrap: wrap; gap: 8px; flex: 1 1 360px; }}
  .callout, blockquote.req {{ max-width: 1000px; }}
  .prose p, .prose li {{ max-width: 96ch; }}
  .prose p {{ margin: 8px 0; }}
  .prose a {{ color: var(--accent); }}
  .part {{ margin-top: 36px; }}
  .partno {{ color: var(--accent); font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    margin: 0 !important; }}
  h2.parth {{ font-size: 25px; margin: 2px 0 6px; }}
  .lede {{ font-size: 16.5px; }}
  h3 {{ font-size: 19.5px; margin: 34px 0 6px; }}
  h3 .sn {{ color: var(--accent); margin-right: 8px; }}
  h4 {{ font-size: 15.5px; margin: 22px 0 4px; }}
  h4 .who {{ font-weight: 400; color: var(--muted); font-size: 13.5px; margin-left: 8px; }}
  blockquote.req {{ margin: 12px 0 8px; padding: 12px 20px; background: var(--surface); border: 1px solid var(--border);
    border-left: 4px solid var(--accent); border-radius: 10px; }}
  .reqt {{ font-size: 17px; font-weight: 700; margin: 4px 0 6px !important; }}
  .reqh {{ font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
    margin: 12px 0 0 !important; }}
  .callout {{ margin: 14px 0; padding: 8px 16px; background: var(--surface); border: 1px solid var(--border);
    border-left: 4px solid var(--violet); border-radius: 10px; }}
  .callout.warnc {{ border-left-color: var(--warn); }}
  .callout.goodc {{ border-left-color: var(--good); }}
  .callout ul, .callout ol {{ margin: 4px 0 8px; padding-left: 22px; }}
  .legend {{ font-size: 14px; color: var(--muted); line-height: 1.9; }}
  .habits li, .steps li {{ margin: 7px 0; }}
  .tw {{ overflow-x: auto; margin: 10px 0 16px; border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface); }}
  table.qt {{ border-collapse: collapse; width: 100%; min-width: 820px; font-size: 14.5px; line-height: 1.45; }}
  table.qt th {{ text-align: left; font-size: 11.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); background: var(--bg); padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  table.qt td {{ vertical-align: top; padding: 9px 12px; border-bottom: 1px solid var(--border); }}
  table.qt tr:last-child td {{ border-bottom: 0; }}
  table.q3 th:nth-child(1) {{ width: 38%; }}
  table.q3 th:nth-child(2) {{ width: 26%; }}
  table.dt5 {{ min-width: 1120px; }}
  table.dt5 th:nth-child(1) {{ width: 12%; }}
  table.dt5 th:nth-child(5) {{ width: 31%; }}
  .tg {{ display: inline-block; font-size: 11.5px; font-weight: 650; line-height: 1.6; padding: 0 7px; border-radius: 999px;
    white-space: nowrap; vertical-align: 1px; }}
  .tg.doc {{ color: var(--good); background: var(--good-soft); }}
  .tg.code {{ color: var(--accent); background: var(--accent-soft); }}
  .tg.asm {{ color: var(--warn); background: var(--warn-soft); }}
  .first {{ color: var(--warn); font-weight: 700; }}
  code {{ font-family: Consolas, Menlo, monospace; font-size: .9em; background: var(--bg); border: 1px solid var(--border);
    border-radius: 4px; padding: 0 4px; }}
  nav a {{ padding: 6px 11px; border: 1px solid var(--border); border-radius: 999px; background: var(--surface);
    color: var(--text); text-decoration: none; font-size: 13.5px; }}
  nav a:hover {{ border-color: var(--accent); }}
  nav a b {{ color: var(--accent); margin-right: 5px; }}
  .why {{ color: var(--accent); font-weight: 600; }}
  .notebg {{ fill: var(--surface); fill-opacity: .9; }}
  .aho {{ fill: none; stroke: currentColor; stroke-opacity: .75; stroke-width: 1.3; }}
  .altsep {{ fill: none; stroke: currentColor; stroke-opacity: .45; stroke-width: 1.1; stroke-dasharray: 6 4; }}
  @media (max-width: 560px) {{ h1 {{ font-size: 23px; }} }}
  .legend .li {{ display: inline-block; margin-right: 14px; }}
  .nw {{ white-space: nowrap; }}
  @media (max-width: 560px) {{
    nav .gl {{ width: auto; }}
    .prose table.qt thead {{ display: none; }}
    .prose table.qt, .prose table.qt tbody, .prose table.qt tr, .prose table.qt td {{ display: block; min-width: 0;
      width: auto; }}
    .prose table.qt tr {{ border-bottom: 1px solid var(--border); padding: 6px 0; }}
    .prose table.qt tr:last-child {{ border-bottom: 0; }}
    .prose table.qt td {{ border: 0; padding: 3px 12px; }}
    .prose table.qt td::before {{ content: attr(data-h); display: block; font-size: 11px; font-weight: 700;
      letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }}
  }}
</style>
</head>
<body>
<header>
  <p class="eyebrow">Requirement → FDE analysis → architecture · The Gen Academy · Week 2, project 2A</p>
  <h1>Enterprise Policy Q&amp;A Bot</h1>
  <p class="src">Drawn from the code at commit <a href="https://github.com/The-Gen-Academy/2A-Enterprise-QandA-Bot/tree/4b2103dcc2ed2c8b09544d84ab396f1ce5e239b0">4b2103d</a>
    and the <a href="https://docs.google.com/document/d/1YnkVkiR9BX8ZBrYo5wG8LWptxbJ44A2-/edit">solution doc</a>.</p>
</header>
{nav}
{body}
</body>
</html>
"""
OUT.write_text(page, encoding="utf-8")
print("written:", OUT, len(FIGS), "figures")
for w in warnings:
    print("WARN", w)
