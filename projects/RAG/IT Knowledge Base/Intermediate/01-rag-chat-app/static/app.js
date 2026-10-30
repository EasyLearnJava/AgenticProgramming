// IT Knowledge Base: the chat page's script. Served at /static/app.js; index.html loads it.
// It loads what the knowledge base holds (GET /api/v1/info) and sends each question (POST /api/v1/query). Each
// request then gets a row of boxes, two side by side: the answer (or what went wrong), and from its trace
// (GET /api/v1/traces/{trace_id}) what happened behind the scenes: the pipeline's steps in the order they ran, the
// time per step on one time scale, every call it made, every log line, and what the model was given. The build at
// start-up gets the same boxes.
"use strict";

// How long the page waits for an answer: the server's own deadline (api.request_timeout_seconds, from
// GET /api/v1/info) and 30 seconds more, so the server's 504 comes first
let requestTimeoutMs = 90000;
let tracesKept = true;     // whether the server keeps traces: GET /api/v1/info says

const statsLine = document.getElementById("stats");
const buildHolder = document.getElementById("build");
const status = document.getElementById("status");
const form = document.getElementById("form");
const input = document.getElementById("question");
const button = document.getElementById("ask");
const counter = document.getElementById("counter");
const samples = document.getElementById("samples");
const empty = document.getElementById("empty");
const answers = document.getElementById("answers");

// A new element with a class and its text. textContent, never innerHTML, so the server's text can't add HTML.
function el(tag, className, text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

// A duration, as people read it: 0 ms, 4.2 ms, 812 ms, 1.05 s
function duration(ms) {
  if (ms === 0) return "0 ms";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`;
}

// A part of a whole, as a share: 17%, or "<1%" for the very small
function share(part, whole) {
  const value = (part / whole) * 100;
  return value > 0 && value < 1 ? "<1%" : `${Math.round(value)}%`;
}

// "1 call", "2 calls"
function count(number, noun, plural = `${noun}s`) {
  return `${number} ${number === 1 ? noun : plural}`;
}

// The line under the box: "busy" while waiting, "error" when something went wrong (with its trace ID), "done"
function setStatus(text, state = "", traceId = "") {
  status.replaceChildren(document.createTextNode(text));
  if (traceId) status.append(el("span", "trace-id", `trace ID ${traceId}`));
  status.dataset.state = state;
}

// How much of the question's limit is used; the limit comes from the server
function updateCounter() {
  counter.textContent = `${input.value.length}/${input.maxLength}`;
}
input.addEventListener("input", updateCounter);
updateCounter();

// What went wrong: the server's error, {"error": {"code", "message", "trace_id", ...}}, or else the HTTP status
async function errorOf(res) {
  try {
    const data = await res.json();
    if (data && data.error) return data.error;
  } catch {
    // not JSON: a proxy's error page, say
  }
  return { message: `The server answered HTTP ${res.status}.`, trace_id: res.headers.get("X-Trace-ID") || "" };
}

// ---------------------------------------------------------------------------------------------------------------
// Reading a trace: its steps in the order they ran, and its calls
// ---------------------------------------------------------------------------------------------------------------

// What each stage is called on the page; a stage not listed here shows its own name
const STAGE_NAMES = {
  "pipeline.query": "Answer the question",
  "retrieval.retrieve": "Find the closest chunks",
  "embeddings.embed_query": "Turn the question into a vector",
  "vectordb.search": "Search the vector store",
  "prompts.build": "Fill in the prompt",
  "llm.generate": "Ask the chat model",
  "pipeline.create": "Make the engine's parts (factory.py)",
  "pipeline.build": "Build the knowledge base",
  "ingestion.load": "Read the knowledge base file",
  "chunking.split": "Cut the articles into chunks",
  "embeddings.load_vectors": "Read the saved vectors",
  "embeddings.embed_documents": "Turn every chunk into a vector",
  "vectordb.recreate": "Make a new, empty collection",
  "vectordb.upsert": "Store each chunk with its vector",
};

// What kind of work a stage is, from its layer; its colour on the page says the same, with this label beside it
const KIND_LABELS = { model: "model call", store: "vector store", app: "the app's own work" };

// Stages in a model's layer that call no model: reading the saved vectors reads a file
const APP_STAGES = new Set(["embeddings.load_vectors"]);

function stageKind(span) {
  if (APP_STAGES.has(span)) return "app";
  const layer = span.split(".")[0];
  if (layer === "embeddings" || layer === "llm") return "model";
  if (layer === "vectordb") return "store";
  return "app";
}

// A field's value as text: lists and objects as JSON, long values cut short
function fieldText(value, limit = 140) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

// One line on what a stage did, from what its span recorded
function stageDetail(event) {
  const f = event.fields;
  if (event.status !== "ok") {
    return `${event.status === "cancelled" ? "stopped (a deadline, or Ctrl+C)" : "failed"}${
      f.error_type ? `: ${f.error_type}` : ""}`;
  }
  switch (event.span) {
    case "embeddings.embed_query": return `${f.model}`;
    case "embeddings.load_vectors":
      return f.used ? `${count(f.vectors, "vector")} from ${f.file}, saved ${f.saved_at}: no call to the model`
        : `not used, so the chunks are embedded: ${f.reason}`;
    case "embeddings.embed_documents": return `${f.model}: ${count(f.texts, "text")}, in ${count(f.batches, "call")}`;
    case "vectordb.search": return `${f.collection}: ${count(f.hits, "chunk")} back, the best scoring ${f.top_score}`;
    case "vectordb.recreate": return `${f.collection}, for vectors of ${f.vector_size} numbers`;
    case "vectordb.upsert": return `${count(f.points, "point")} into ${f.collection}`;
    case "retrieval.retrieve": return `the ${f.top_k} closest: ${(f.found || []).join(", ")} (article#chunk)`;
    case "prompts.build":
      return `${count(f.chunks, "chunk")} and the question: ${f.prompt_chars} characters (${f.prompt_version})`;
    case "llm.generate":
      return `${f.model}: ${f.input_tokens ?? "?"} tokens in, ${f.output_tokens ?? "?"} out; stopped: ${
        f.finish_reason ?? "?"}`;
    case "pipeline.query":
      return `${count(f.sources, "source")}, an answer of ${f.answer_chars} characters`;
    case "ingestion.load": return `${f.file}: ${count(f.documents, "article")}`;
    case "chunking.split": return `${count(f.chunks, "chunk")}, ${f.min_chars} to ${f.max_chars} characters each`;
    case "pipeline.build": return `${count(f.documents, "article")}, ${count(f.chunks, "chunk")}`;
    case "pipeline.create": return `${f.embedding_model} and ${f.chat_model}, from ${f.embeddings}, ${f.llm} and ${
      f.vectordb}: their clients, made, and no call to them yet`;
    default: return Object.entries(f).map(([key, value]) => `${key}=${fieldText(value)}`).join(" ");
  }
}

// httpx's line for each HTTP call: HTTP Request: POST https://host/path "HTTP/1.1 200 OK"
const HTTP_LINE = /^HTTP Request: (\S+) (\S+) "\S+ (\d+) ([^"]*)"$/;

// Everything the boxes show, read from one trace: its stages, the pipeline's steps in the order they ran (the
// stages with no stage inside them, between the request coming in and the response going out), and its calls
function readTrace(trace) {
  const events = trace.events;
  const started = events.find((event) => event.message === "Request started");
  const finished = events.find((event) => event.message === "Request finished");
  const spans = events.filter((event) => event.span);
  // The whole request's time: a stage ends at its start plus its duration; any other line, where it was written
  const total = Math.max(0.1, finished?.duration_ms ?? 0, ...spans.map((event) => event.at_ms + event.duration_ms),
                         ...events.map((event) => event.logged_ms));
  const inside = (outer, inner) => inner !== outer && inner.depth > outer.depth &&
    inner.at_ms >= outer.at_ms - 0.2 && inner.at_ms + inner.duration_ms <= outer.at_ms + outer.duration_ms + 0.2;
  const leaves = spans.filter((outer) => !spans.some((inner) => inside(outer, inner)));

  const steps = [];
  if (started) {
    steps.push({ kind: "app", name: "Receive the request", at: started.logged_ms, ms: null, status: "ok",
                 detail: `${started.fields.method} ${started.fields.path}` });
  }
  for (const event of leaves) {
    steps.push({ kind: stageKind(event.span), name: STAGE_NAMES[event.span] || event.span, span: event.span,
                 at: event.at_ms, ms: event.duration_ms, status: event.status, detail: stageDetail(event) });
  }
  if (finished) {
    const code = finished.fields.status_code;
    steps.push({ kind: "app", name: "Send the response", at: finished.logged_ms, ms: null,
                 status: code >= 400 ? "failed" : "ok", detail: `${code}, ${duration(finished.duration_ms)} in all` });
  }
  steps.forEach((step, index) => { step.number = index + 1; });

  // Each log line belongs to the step that last started at or before it was written
  const stepOf = (event) => steps.reduce((found, step) => (step.at <= event.logged_ms + 0.05 ? step : found), steps[0]);

  const http = events.filter((event) => event.logger.startsWith("httpx")).map((event) => HTTP_LINE.exec(event.message))
    .filter(Boolean).map(([, method, url, code, reason]) => ({ method, url, code: Number(code), reason }));
  const generate = spans.find((event) => event.span === "llm.generate");
  const calls = {
    model: leaves.filter((event) => stageKind(event.span) === "model"),
    store: leaves.filter((event) => stageKind(event.span) === "store"),
    http,
    retries: events.filter((event) => event.logger.startsWith("google_genai") && event.message.startsWith("Retrying")),
    failed: leaves.filter((event) => event.status !== "ok"),
    tokens: generate && generate.fields.input_tokens != null
      ? { input: generate.fields.input_tokens, output: generate.fields.output_tokens } : null,
  };
  return { events, spans, leaves, steps, total, finished, stepOf, calls };
}

// ---------------------------------------------------------------------------------------------------------------
// The boxes
// ---------------------------------------------------------------------------------------------------------------

// A box: its number, its title and a line on what it shows, then its content
function box(number, title, help, ...content) {
  const node = el("article", "box");
  const head = el("header", "box-head");
  head.append(el("span", "box-number", String(number)), el("h3", "box-title", title));
  node.append(head);
  if (help) node.append(el("p", "box-help", help));
  node.append(...content);
  return node;
}

// A kind's swatch and its name: the colour marks it, the text names it
function kindLabel(kind) {
  const label = el("span", "kind-label");
  const swatch = el("i", "swatch");
  swatch.dataset.kind = kind;
  label.append(swatch, document.createTextNode(KIND_LABELS[kind]));
  return label;
}

// The key to the colours: one swatch per kind of work
function legend() {
  const row = el("p", "legend");
  row.append(...["model", "store", "app"].map(kindLabel));
  return row;
}

// How a stage that didn't end well ended: an icon and a word, never the colour alone
function outcomeLabel(stateName) {
  const label = el("span", "outcome-label");
  label.dataset.status = stateName;
  label.append(el("span", "outcome-icon", stateName === "cancelled" ? "■" : "✕"),
               document.createTextNode(stateName === "cancelled" ? "stopped" : "failed"));
  return label;
}

// A bar on one time scale: where it starts and how long it lasts, as shares of the whole
function bar(start, length, total, kind, stateName, title) {
  const track = el("span", "track");
  const fill = el("span", "fill");
  fill.dataset.kind = kind;
  fill.dataset.status = stateName;
  fill.style.left = `${Math.min((start / total) * 100, 99.6)}%`;
  fill.style.width = `${Math.max((length / total) * 100, 0.4)}%`;
  fill.title = title;
  track.append(fill);
  return track;
}

// 1. The answer: what the model wrote, and the articles the search found
function answerBox(data) {
  const list = el("ol", "sources");
  for (const source of data.sources) {
    const head = el("div", "source-head");
    head.append(el("strong", "source-title", source.title), el("span", "tag", source.system),
                el("span", "tag", source.category), el("span", "source-score", `score ${source.score.toFixed(3)}`));
    const item = el("li", "source");
    item.append(head, el("p", "source-snippet", source.snippet));
    list.append(item);
  }
  return box(1, "The answer", "What the model wrote, then the articles the search found: what the model was " +
             "given, not a checked list of what the answer used.", el("p", "card-answer", data.answer),
             el("p", "sources-label", "Found by the search"), list);
}

// 1. Or what went wrong: the server's message, its code, and whether trying again may work
function failureBox(error) {
  const message = el("p", "failure");
  message.append(el("span", "outcome-icon", "✕"), document.createTextNode(error.message));
  const facts = el("p", "box-help", `${error.code || "No code"}; ${error.retryable
    ? "trying again later may work." : "trying again won't help until it's fixed."}`);
  return box(1, "What went wrong", "The server's message for this request. Boxes 2 to 6 show where it went wrong.",
             message, facts);
}

// 1, once the trace is read: where a failed request went wrong, and why, as the server's log says
function whereItFailed(trace) {
  const step = trace.steps.find((candidate) => candidate.status !== "ok" && candidate.ms !== null);
  const failure = trace.events.find((event) => /^Request (failed|refused)/.test(event.message));
  const parts = [];
  if (step) {
    parts.push(el("p", "where", `Where: step ${step.number}, ${step.name.toLowerCase()} (${step.span}), after ${
      duration(step.ms)}.`));
  }
  if (failure?.fields.error) {
    parts.push(el("p", "prompt-role", "The server's log says"), el("pre", "prompt-text", failure.fields.error));
  } else if (failure?.fields.fields) {
    parts.push(el("p", "where", `The fields it refused: ${failure.fields.fields.join(", ")}.`));
  }
  return parts;
}

// 2. The pipeline: each step in the order it ran, with its time and its share of the whole request
function pipelineBox(number, trace) {
  const list = el("ol", "pipeline");
  for (const step of trace.steps) {
    const item = el("li", "pipe-step");
    item.dataset.kind = step.kind;
    item.dataset.status = step.status;
    const head = el("div", "pipe-head");
    head.append(el("span", "pipe-name", step.name), kindLabel(step.kind));
    if (step.status !== "ok") head.append(outcomeLabel(step.status));
    head.append(el("span", "pipe-time", step.ms === null ? `at ${duration(step.at)}`
      : `${duration(step.ms)} · ${share(step.ms, trace.total)}`));
    const body = el("div", "pipe-body");
    body.append(head);
    if (step.ms !== null) {
      body.append(bar(0, step.ms, trace.total, step.kind, step.status,
                      `${step.name}: ${duration(step.ms)}, ${share(step.ms, trace.total)} of ${duration(trace.total)}`));
    }
    if (step.detail) body.append(el("p", "pipe-detail", step.detail));
    const marker = el("span", "pipe-marker", String(step.number));
    marker.dataset.kind = step.kind;
    item.append(marker, body);
    list.append(item);
  }
  return box(number, "Pipeline", "Each step, numbered in the order it ran. Its bar is its share of the whole " +
             `request (${duration(trace.total)}).`, legend(), list);
}

// 3. The time per step: every stage on one time scale, indented under the stage it's part of
function timeBox(number, trace) {
  const rows = [];
  const offset = trace.finished ? 1 : 0;
  if (trace.finished) {
    rows.push({ name: "The whole request", kind: "app", at: 0, ms: trace.finished.duration_ms, depth: 0,
                status: trace.finished.fields.status_code >= 400 ? "failed" : "ok" });
  }
  for (const event of trace.spans) {
    rows.push({ name: STAGE_NAMES[event.span] || event.span, at: event.at_ms, ms: event.duration_ms,
                kind: trace.leaves.includes(event) ? stageKind(event.span) : "app", depth: event.depth + offset,
                status: event.status, leaf: trace.leaves.includes(event) });
  }
  const slowest = rows.filter((row) => row.leaf).reduce((top, row) => (top && top.ms >= row.ms ? top : row), null);

  const chart = el("div", "gantt");
  const axis = el("div", "gantt-row gantt-axis");
  const ticks = el("span", "track ticks");
  for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
    const tick = el("span", "tick", duration(trace.total * fraction));
    tick.style.left = `${fraction * 100}%`;
    ticks.append(tick);
  }
  axis.append(el("span", "gantt-name", ""), ticks, el("span", "gantt-time", ""));
  chart.append(axis);
  for (const row of rows) {
    const line = el("div", "gantt-row");
    line.dataset.status = row.status;
    const name = el("span", "gantt-name", row.name);
    name.style.paddingLeft = `${row.depth * 14}px`;
    const time = el("span", "gantt-time", duration(row.ms));
    if (row === slowest) time.append(el("span", "slowest", "slowest"));
    line.append(name, bar(row.at, row.ms, trace.total, row.kind, row.status,
                          `${row.name}: from ${duration(row.at)} to ${duration(row.at + row.ms)}`), time);
    chart.append(line);
  }
  const headline = slowest
    ? `Most of the time went to ${slowest.name.toLowerCase()}: ${duration(slowest.ms)}, ${
      share(slowest.ms, trace.total)} of the whole.` : "";
  return box(number, "Time per step", "When each stage started and how long it took, on one time scale; a stage's " +
             "own steps sit indented under it.", el("p", "headline", headline), chart, legend());
}

// One count, with what it's made of: a label, the number, a dot per call, and a line of detail
function tile(label, value, dots, detail) {
  const node = el("div", "tile");
  node.append(el("p", "tile-label", label), el("p", "tile-value", String(value)));
  if (dots.length) {
    const row = el("p", "tile-dots");
    for (const dot of dots) {
      const mark = el("i", "dot");
      mark.dataset.kind = dot.kind;
      mark.dataset.status = dot.status;
      mark.title = dot.title;
      row.append(mark);
    }
    node.append(row);
  }
  if (detail) node.append(el("p", "tile-detail", detail));
  return node;
}

// 4. The calls: how many of each kind this request made; each dot is one call
function callsBox(number, trace) {
  const c = trace.calls;
  const modelDots = c.model.flatMap((event) => Array.from({ length: event.fields.batches || 1 }, () => ({
    kind: "model", status: event.status, title: `${STAGE_NAMES[event.span] || event.span}: ${event.fields.model}` })));
  const byModel = Object.entries(Object.groupBy(modelDots, (dot) => dot.title.split(": ")[1]))
    .map(([model, dots]) => `${model} ×${dots.length}`).join(", ");
  const codes = Object.entries(Object.groupBy(c.http, (call) => `${call.code} ${call.reason}`))
    .map(([code, calls]) => `${code} ×${calls.length}`).join(", ");
  const hosts = [...new Set(c.http.map((call) => { try { return new URL(call.url).host; } catch { return call.url; } }))];
  const tiles = el("div", "tiles");
  tiles.append(
    tile("Model calls", modelDots.length, modelDots, byModel || "none"),
    tile("HTTP requests", c.http.length, c.http.map((call) => ({
      kind: "model", status: call.code >= 400 ? "failed" : "ok", title: `${call.method} ${call.url}: ${call.code}` })),
      c.http.length ? `${codes}
to ${hosts.join(", ")}` : "none"),
    tile("Vector store calls", c.store.length, c.store.map((event) => ({
      kind: "store", status: event.status, title: STAGE_NAMES[event.span] || event.span })),
      c.store.map((event) => event.span.split(".")[1]).join(", ") || "none"),
    tile("Tokens", c.tokens ? c.tokens.input + c.tokens.output : 0, [], c.tokens
      ? `${c.tokens.input} in, ${c.tokens.output} out`
      : trace.spans.some((event) => event.span === "llm.generate") ? "none reported: the chat model's call failed"
        : "no chat model call"),
    tile("Retries", c.retries.length, [], c.retries.length ? "Google's client tried a call again" : "none needed"),
    tile("Tool calls", 0, [], "none: the model is given no tools, only the prompt"),
    tile("Failed steps", c.failed.length, c.failed.map((event) => ({
      kind: stageKind(event.span), status: "failed", title: `${event.span}: ${event.fields.error_type ?? ""}` })),
      c.failed.map((event) => `${event.span}: ${event.fields.error_type ?? event.status}`).join("; ") || "none"),
  );
  return box(number, "Calls", "How many calls this request made, of each kind. Each dot is one call; a red one " +
             "failed.", tiles);
}

// 5. The logs: every line, in the order the server wrote them, each with the pipeline step it belongs to
function logsBox(number, trace) {
  const list = el("ol", "log-lines");
  [...trace.events].sort((a, b) => a.logged_ms - b.logged_ms).forEach((event, index) => {
    const step = trace.stepOf(event);
    const fields = Object.entries(event.fields).map(([key, value]) => `${key}=${fieldText(value)}`);
    if (event.span) fields.unshift(`duration_ms=${event.duration_ms}`);
    const line = el("li", "log-line");
    line.dataset.level = event.level;
    const badge = el("span", "log-step", step ? String(step.number) : "");
    if (step) {
      badge.dataset.kind = step.kind;
      badge.title = `Step ${step.number}: ${step.name}`;
    }
    line.append(el("span", "log-index", String(index + 1)), el("span", "log-time", `+${event.logged_ms.toFixed(1)} ms`),
                badge, el("span", "log-level", event.level),
                el("span", "log-text", `${event.logger}: ${event.message}${fields.length ? `  ${fields.join(" ")}` : ""}${
                  event.error ? `  error=${event.error}` : ""}`));
    list.append(line);
  });
  const dropped = trace.dropped ? ` (and ${trace.dropped} more not kept)` : "";
  return box(number, "Logs", `All ${trace.events.length} lines the server wrote for this request${dropped}, in the ` +
             "order it wrote them. The number in the circle is the pipeline step each line belongs to.", list);
}

// 6. What the model was given: the chunks the search found, and the prompt they went into
function inputBox(number, trace) {
  const found = trace.events.filter((event) => event.message === "Chunk found");
  const prompt = trace.events.find((event) => event.message === "Prompt");
  const content = [];
  if (found.length) {
    const table = el("table", "chunks-table");
    const head = el("tr", "");
    for (const title of ["#", "Article", "Chunk", "Score"]) head.append(el("th", "", title));
    table.append(head);
    for (const event of found) {
      const f = event.fields;
      const row = el("tr", "");
      row.append(el("td", "", String(f.rank)), el("td", "", f.title ?? ""), el("td", "", f.chunk ?? ""),
                 el("td", "", Number(f.score).toFixed(3)));
      table.append(row);
    }
    content.push(table);
  }
  const roles = { system: "System message: the rules, then the chunks found", human: "Human message: the question" };
  for (const message of prompt?.fields.messages || []) {
    content.push(el("p", "prompt-role", roles[message.role] || message.role), el("pre", "prompt-text", message.content));
  }
  if (!content.length) content.push(el("p", "box-help", "Nothing: the request stopped before the search."));
  return box(number, "What the model was given", "The chunks the search found, best first, then the prompt " +
             "they went into, exactly as sent.", ...content);
}

// ---------------------------------------------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------------------------------------------

// Read a trace from the server; null (with why, in `holder`) if it can't be read
async function readTraceFrom(traceId, holder) {
  try {
    const res = await fetch(`/api/v1/traces/${encodeURIComponent(traceId)}`);
    if (!res.ok) throw new Error((await errorOf(res)).message);
    const raw = await res.json();
    return { ...readTrace(raw), dropped: raw.dropped };
  } catch (err) {
    holder.append(el("p", "box-help", `The trace isn't available: ${err.message}`));
    return null;
  }
}

// One summary chip in a request's head
function chip(text, className = "") {
  return el("span", `chip ${className}`.trim(), text);
}

// Only the newest request stays open, so the older ones don't push the page long; click one to open it again
function closeOlderRequests() {
  for (const section of answers.querySelectorAll("details.request[open]")) section.open = false;
}

// One request: a head (the question, how it went, its trace ID), then its boxes, two side by side
async function showRequest(question, outcome) {
  const section = el("details", "request");
  section.open = true;
  const head = el("summary", "request-head");
  const chips = el("span", "request-chips");
  chips.append(chip(outcome.ok ? `answered · ${outcome.statusCode}` : `failed · ${outcome.statusCode}`,
                    outcome.ok ? "chip-ok" : "chip-failed"),
               chip(`${(outcome.milliseconds / 1000).toFixed(1)} s`));
  if (outcome.traceId) chips.append(chip(`trace ID ${outcome.traceId}`, "trace-id"));
  head.append(el("span", "request-label", "You asked"),
              el("span", "request-question", question.trim() || "(an empty question)"), chips);
  const boxes = el("div", "boxes");
  boxes.append(outcome.ok ? answerBox(outcome.data) : failureBox(outcome.error));
  section.append(head, boxes);
  closeOlderRequests();
  answers.prepend(section);
  if (!tracesKept || !outcome.traceId) return;

  const waiting = box(2, "Behind the scenes", "Reading this request's trace…");
  boxes.append(waiting);
  const trace = await readTraceFrom(outcome.traceId, waiting);
  if (!trace) return;
  waiting.replaceWith(pipelineBox(2, trace), timeBox(3, trace), callsBox(4, trace), logsBox(5, trace),
                      inputBox(6, trace));
  if (!outcome.ok) boxes.firstElementChild.append(...whereItFailed(trace));
  const modelCalls = trace.calls.model.reduce((sum, event) => sum + (event.fields.batches || 1), 0);
  chips.append(chip(count(trace.steps.length, "step")), chip(count(modelCalls, "model call")),
               chip(count(trace.events.length, "log line")));
}

// The build at start-up, as its own row of boxes: how the knowledge base was built
async function showBuild(traceId) {
  const section = el("details", "request build");
  const head = el("summary", "request-head");
  const chips = el("span", "request-chips");
  head.append(el("span", "request-label", "At start-up"), el("span", "request-question",
              "How the knowledge base was built"), chips);
  const boxes = el("div", "boxes");
  section.append(head, boxes);
  buildHolder.append(section);
  const trace = await readTraceFrom(traceId, boxes);
  if (!trace) return;
  boxes.append(pipelineBox(1, trace), timeBox(2, trace), callsBox(3, trace), logsBox(4, trace));
  const modelCalls = trace.calls.model.reduce((sum, event) => sum + (event.fields.batches || 1), 0);
  chips.append(chip(duration(trace.total)), chip(count(trace.steps.length, "step")),
               chip(count(modelCalls, "model call")), chip(count(trace.events.length, "log line")));
}

// On load: what the server holds, as a row of small labels; the question's limit; the sample questions; and how the
// knowledge base was built, from the build's trace
async function loadInfo() {
  try {
    const res = await fetch("/api/v1/info");
    if (!res.ok) throw new Error((await errorOf(res)).message);
    const info = await res.json();
    statsLine.replaceChildren(...[
      `${info.documents} articles`, `${info.chunks} chunks`, `${info.top_k} chunks per question`,
      `answers by ${info.chat_model}`, `search by ${info.embedding_model}`,
    ].map((text) => el("span", "pill", text)));
    input.maxLength = info.max_question_length;
    samples.replaceChildren(...info.sample_questions.map((question) => {
      const sample = el("button", "chip-button", question);
      sample.type = "button";
      sample.addEventListener("click", () => {
        if (button.disabled) return;          // not while another question is being answered
        input.value = question;
        updateCounter();
        form.requestSubmit();
      });
      return sample;
    }));
    if (!input.value) input.value = info.sample_questions[0] || "";
    updateCounter();
    tracesKept = info.traces;
    requestTimeoutMs = (info.request_timeout_seconds + 30) * 1000;
    if (info.traces && info.build_trace_id) showBuild(info.build_trace_id);
  } catch (err) {
    statsLine.textContent = `Couldn't load the knowledge base's info: ${err.message}`;
  }
}
loadInfo();

// While waiting: a card with the question and shimmering lines where the answer will go
function showPending(question) {
  const card = el("article", "card pending");
  card.setAttribute("aria-hidden", "true");
  card.append(el("p", "card-label", "Asking"), el("h2", "card-question", question),
              el("div", "line"), el("div", "line"));
  answers.prepend(card);
  empty.hidden = true;
  return card;
}

// Each submit: send the question, then show the answer or what went wrong, with what happened behind the scenes
form.addEventListener("submit", async (event) => {
  event.preventDefault();                     // stay on this page: the form would otherwise reload it
  const question = input.value;
  button.disabled = true;                     // one question at a time: each one is a real call to the model
  setStatus("Searching the knowledge base and asking the model", "busy");
  const pending = showPending(question);
  const started = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), requestTimeoutMs);
  try {
    const res = await fetch("/api/v1/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });
    pending.remove();
    const milliseconds = performance.now() - started;
    if (res.ok) {
      setStatus("Done.", "done");
      await showRequest(question, { ok: true, statusCode: res.status, data: await res.json(), milliseconds,
                                    traceId: res.headers.get("X-Trace-ID") || "" });
    } else {
      const error = await errorOf(res);       // 422, 502, 503, 504, ...: the server's message says what to do
      setStatus(error.message, "error", error.trace_id);
      await showRequest(question, { ok: false, statusCode: res.status, error, milliseconds,
                                    traceId: error.trace_id || "" });
    }
  } catch (err) {
    setStatus(err.name === "AbortError"
      ? `No answer after ${requestTimeoutMs / 1000} seconds. Try again in a moment.`
      : `Couldn't reach the server: ${err.message}`, "error");
  } finally {
    clearTimeout(timer);
    pending.remove();
    empty.hidden = answers.children.length > 0;   // back to the hint if nothing has been answered yet
    button.disabled = false;
    input.focus();
  }
});
