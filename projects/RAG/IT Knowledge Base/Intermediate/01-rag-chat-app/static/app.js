// IT Knowledge Base: the chat page's script. Served at /static/app.js; index.html loads it.
// It loads what the knowledge base holds (GET /api/v1/info), sends each question (POST /api/v1/query), and shows the
// answer with its sources; or what went wrong. Under each, "Behind the scenes" shows that request's trace (GET
// /api/v1/traces/{trace_id}): every stage on a timeline, every call to the models, the chunks found, the prompt, and
// every log line the server wrote for it.
"use strict";

// How long the page waits for an answer: the server's own deadline (api.request_timeout_seconds, from
// GET /api/v1/info) and 30 seconds more, so the server's 504 comes first
let requestTimeoutMs = 90000;

const statsLine = document.getElementById("stats");
const buildPanel = document.getElementById("build");
const status = document.getElementById("status");
const form = document.getElementById("form");
const input = document.getElementById("question");
const button = document.getElementById("ask");
const counter = document.getElementById("counter");
const samples = document.getElementById("samples");
const empty = document.getElementById("empty");
const answers = document.getElementById("answers");

let tracesKept = true;     // whether the server keeps traces: GET /api/v1/info says

// A new element with a class and its text. textContent, never innerHTML, so the server's text can't add HTML.
function el(tag, className, text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

// A duration, as people read it: 4.2 ms, 812 ms, 1.05 s
function duration(ms) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`;
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
// Behind the scenes: one request's trace
// ---------------------------------------------------------------------------------------------------------------

// What each stage is called on the page; a stage not listed here shows its own name
const STAGE_NAMES = {
  "pipeline.query": "Answer the question",
  "retrieval.retrieve": "Find the chunks closest to the question",
  "embeddings.embed_query": "Turn the question into a vector",
  "vectordb.search": "Search the vector store",
  "llm.generate": "Ask the chat model, with the chunks found",
  "pipeline.build": "Build the knowledge base",
  "ingestion.load": "Read the knowledge base file",
  "chunking.split": "Cut the articles into chunks",
  "embeddings.embed_documents": "Turn every chunk into a vector",
  "vectordb.recreate": "Make a new, empty collection",
  "vectordb.upsert": "Store each chunk with its vector",
};

// What kind of work a stage is, from its layer: a call to a model, the vector store, or the app's own work
function stageKind(span) {
  const layer = span.split(".")[0];
  if (layer === "embeddings" || layer === "llm") return "model call";
  if (layer === "vectordb") return "vector store";
  return "";
}

// A field's value as text: lists and objects as JSON, long values cut short
function fieldText(value, limit = 160) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

// One line on what a stage did, from what its span recorded
function stageDetail(event) {
  const f = event.fields;
  if (event.status !== "ok") return `${event.status === "cancelled" ? "stopped by the deadline" : "failed"}${
    f.error_type ? `: ${f.error_type}` : ""}`;
  switch (event.span) {
    case "embeddings.embed_query": return `${f.model}`;
    case "embeddings.embed_documents":
      return `${f.model}: ${f.texts} texts, in ${f.batches} call${f.batches === 1 ? "" : "s"}`;
    case "vectordb.search": return `${f.collection}: ${f.hits} chunks back, the best scoring ${f.top_score}`;
    case "vectordb.recreate": return `${f.collection}, for vectors of ${f.vector_size} numbers`;
    case "vectordb.upsert": return `${f.points} points into ${f.collection}`;
    case "retrieval.retrieve": return `the ${f.top_k} closest: ${(f.found || []).join(", ")} (article#chunk)`;
    case "llm.generate":
      return `${f.model}: ${f.input_tokens ?? "?"} tokens in, ${f.output_tokens ?? "?"} out; stopped: ${
        f.finish_reason ?? "?"}`;
    case "pipeline.query":
      return `prompt ${f.prompt_version}; ${f.sources} sources; an answer of ${f.answer_chars} characters`;
    case "ingestion.load": return `${f.file}: ${f.documents} articles`;
    case "chunking.split": return `${f.chunks} chunks, ${f.min_chars} to ${f.max_chars} characters each`;
    case "pipeline.build": return `${f.documents} articles, ${f.chunks} chunks`;
    default: return Object.entries(f).map(([key, value]) => `${key}=${fieldText(value)}`).join(" ");
  }
}

// Lines worth a row on the timeline besides the stages: warnings and errors, the request's failure, and the
// libraries' own lines (httpx's line for each HTTP call to the models, Google's retries)
function isNote(event) {
  if (event.span) return false;
  if (event.level === "WARNING" || event.level === "ERROR" || event.level === "CRITICAL") return true;
  if (/^Request (failed|refused)/.test(event.message)) return true;
  return !/^(src|main)(\.|$)/.test(event.logger);
}

// One row of the timeline: what happened, a bar for when and how long, and a line of detail
function timelineRow(name, kind, event, start, length, total, detail) {
  const row = el("li", "step");
  row.dataset.status = event.status || (event.level === "ERROR" ? "error" : event.level === "WARNING" ? "warning" : "ok");
  row.style.setProperty("--depth", String(event.depth));
  const head = el("div", "step-head");
  head.append(el("span", "step-name", name));
  if (kind) head.append(el("span", "step-kind", kind));
  if (event.span) head.append(el("code", "step-span", event.span));
  head.append(el("span", "step-time", length === null ? `at ${duration(start)}` : duration(length)));
  const bar = el("div", "step-bar");
  const fill = el("span", "");
  fill.style.left = `${Math.min((start / total) * 100, 99.5)}%`;
  fill.style.width = length === null ? "3px" : `${Math.max((length / total) * 100, 0.5)}%`;
  bar.append(fill);
  row.append(head, bar);
  if (detail) row.append(el("p", "step-detail", detail));
  return row;
}

// httpx's line for each HTTP call: HTTP Request: POST https://host/path "HTTP/1.1 200 OK"
const HTTP_LINE = /^HTTP Request: (\S+) (\S+) "\S+ (\d+) ([^"]*)"$/;

// A note's row: an HTTP call to a model's service, a retry by Google's client, a failure (with why), or a warning
function noteRow(event, total) {
  const call = event.logger.startsWith("httpx") ? HTTP_LINE.exec(event.message) : null;
  if (call) {
    const [, method, url, code, reason] = call;
    let host = "the model's service", path = url;
    try {
      ({ host, pathname: path } = new URL(url));
    } catch {
      // not a URL the browser can read: shown as it came
    }
    return timelineRow(`Call to ${host}`, "HTTP call", { ...event, status: Number(code) >= 400 ? "error" : "ok" },
                       event.at_ms, null, total, `${method} ${path}: answered ${code} ${reason}`);
  }
  if (event.logger.startsWith("google_genai") && event.message.startsWith("Retrying")) {
    return timelineRow("Google's client tries the call again", "retry", { ...event, status: "warning" }, event.at_ms,
                       null, total, event.message);
  }
  const f = event.fields;
  const detail = f.error || (f.fields ? `the fields: ${f.fields.join(", ")}` : "") || event.error || "";
  const failed = /^Request (failed|refused)/.test(event.message) && event.level !== "ERROR";
  return timelineRow(event.message, event.level.toLowerCase(), failed ? { ...event, status: "warning" } : event,
                     event.at_ms, null, total, detail);
}

// The chunks the search found: rank, article, chunk and score
function chunkTable(found) {
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
  return table;
}

// The prompt, message by message, exactly as the model got it
function promptView(event) {
  const view = el("div", "prompt");
  const roles = { system: "System message: the rules, then the chunks found", human: "Human message: the question" };
  for (const message of event.fields.messages || []) {
    view.append(el("p", "prompt-role", roles[message.role] || message.role), el("pre", "prompt-text", message.content));
  }
  return view;
}

// Every log line, in the order the server wrote them, as its console shows them
function logLines(events) {
  const list = el("ol", "log-lines");
  for (const event of [...events].sort((a, b) => a.logged_ms - b.logged_ms)) {
    const fields = Object.entries(event.fields).map(([key, value]) => `${key}=${fieldText(value)}`);
    if (event.span) fields.unshift(`duration_ms=${event.duration_ms}`);
    const line = el("li", "log-line", `+${event.logged_ms.toFixed(1)} ms  ${event.level.padEnd(7)} ${event.logger}: ` +
      `${event.message}${fields.length ? `  ${fields.join(" ")}` : ""}${event.error ? `  error=${event.error}` : ""}`);
    line.dataset.level = event.level;
    list.append(line);
  }
  return list;
}

// A part of the panel that opens on a click
function part(title, content, open = false) {
  const details = el("details", "trace-part");
  details.open = open;
  details.append(el("summary", "", title), content);
  return details;
}

// One request's trace as a panel: a summary, the timeline, then the chunks, the prompt and every log line
function renderTrace(trace, title, open) {
  const events = trace.events;
  const finished = events.find((event) => event.message === "Request finished");
  const total = Math.max(1, finished?.duration_ms ?? 0, ...events.map((event) => event.at_ms + (event.duration_ms || 0)));
  const stages = events.filter((event) => event.span);
  const modelCalls = stages.filter((event) => stageKind(event.span) === "model call").length;

  const panel = el("details", "trace");
  panel.open = open;
  const summary = el("summary", "trace-summary");
  summary.append(el("span", "trace-title", title), ...[
    `${stages.length} stage${stages.length === 1 ? "" : "s"}`,
    `${modelCalls} model call${modelCalls === 1 ? "" : "s"}`,
    `${events.length} log line${events.length === 1 ? "" : "s"}`,
    duration(finished?.duration_ms ?? total),
  ].map((text) => el("span", "trace-badge", text)));

  const timeline = el("ol", "steps");
  if (finished) {
    const f = finished.fields;
    const outcome = f.status_code >= 500 ? "error" : f.status_code >= 400 ? "warning" : "ok";
    timeline.append(timelineRow("The whole request", "HTTP", { ...finished, status: outcome }, 0, finished.duration_ms,
                                total, `${f.method} ${f.path}: answered ${f.status_code}`));
  }
  for (const event of events) {
    if (event.span) {
      timeline.append(timelineRow(STAGE_NAMES[event.span] || event.span, stageKind(event.span), event, event.at_ms,
                                  event.duration_ms, total, stageDetail(event)));
    } else if (isNote(event)) {
      timeline.append(noteRow(event, total));
    }
  }

  const body = el("div", "trace-body");
  body.append(el("p", "trace-help", "Each stage the server ran for this request, in order, with how long it took " +
                 "(the bars share one time scale). Read from the top: a stage's own steps sit indented under it."),
              timeline);
  const found = events.filter((event) => event.message === "Chunk found");
  if (found.length) body.append(part(`The ${found.length} chunks the search found`, chunkTable(found)));
  const prompt = events.find((event) => event.message === "Prompt");
  if (prompt) body.append(part("The prompt the model was given", promptView(prompt)));
  const kept = trace.dropped ? ` (and ${trace.dropped} not kept)` : "";
  body.append(part(`Every log line the server wrote: ${events.length}${kept}`, logLines(events), true));
  panel.append(summary, body);
  return panel;
}

// Read a request's trace from the server and show it at the end of `holder`; or say why it isn't there
async function showTrace(holder, traceId, title, open) {
  if (!tracesKept || !traceId) return;
  const waiting = el("p", "trace-waiting", "Reading what happened behind the scenes…");
  holder.append(waiting);
  try {
    const res = await fetch(`/api/v1/traces/${encodeURIComponent(traceId)}`);
    if (!res.ok) throw new Error((await errorOf(res)).message);
    waiting.replaceWith(renderTrace(await res.json(), title, open));
  } catch (err) {
    waiting.textContent = `The trace isn't available: ${err.message}`;
  }
}

// ---------------------------------------------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------------------------------------------

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
      const chip = el("button", "chip", question);
      chip.type = "button";
      chip.addEventListener("click", () => {
        if (button.disabled) return;          // not while another question is being answered
        input.value = question;
        updateCounter();
        form.requestSubmit();
      });
      return chip;
    }));
    if (!input.value) input.value = info.sample_questions[0] || "";
    updateCounter();
    tracesKept = info.traces;
    requestTimeoutMs = (info.request_timeout_seconds + 30) * 1000;
    if (info.build_trace_id) showTrace(buildPanel, info.build_trace_id, "How the knowledge base was built", false);
  } catch (err) {
    statsLine.textContent = `Couldn't load the knowledge base's info: ${err.message}`;
  }
}
loadInfo();

// Under each answer or failure: its trace ID and how long it took
function cardMeta(traceId, milliseconds, verb) {
  const meta = el("p", "card-meta");
  if (traceId) meta.append(el("span", "trace-id", `trace ID ${traceId}`));
  meta.append(el("span", "", `${verb} in ${(milliseconds / 1000).toFixed(1)} s`));
  return meta;
}

// Only the newest card's panel stays open, so the older ones don't push the page long
function closeOlderTraces() {
  for (const panel of answers.querySelectorAll("details.trace[open]")) panel.open = false;
}

// One answer, newest first: the question, the answer, each article the search found, then its trace
function showAnswer(question, data, traceId, milliseconds) {
  const card = el("article", "card");
  const list = el("ol", "sources");
  for (const source of data.sources) {
    const head = el("div", "source-head");
    head.append(el("strong", "source-title", source.title), el("span", "tag", source.system),
                el("span", "tag", source.category));
    const item = el("li", "source");
    item.append(head, el("p", "source-snippet", source.snippet));
    list.append(item);
  }
  card.append(el("p", "card-label", "You asked"), el("h2", "card-question", question),
              el("p", "card-answer", data.answer), el("p", "sources-label", "Found by the search"), list,
              cardMeta(traceId, milliseconds, "answered"));
  closeOlderTraces();
  answers.prepend(card);
  showTrace(card, traceId, "Behind the scenes", true);
}

// A question that wasn't answered gets a card too: what went wrong, then its trace, which shows where
function showFailure(question, error, milliseconds) {
  const card = el("article", "card card-failed");
  card.append(el("p", "card-label", "You asked"), el("h2", "card-question", question),
              el("p", "card-error", error.message), cardMeta(error.trace_id, milliseconds, "failed"));
  closeOlderTraces();
  answers.prepend(card);
  showTrace(card, error.trace_id, "Behind the scenes", true);
}

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

// Each submit: send the question, then show the answer or what went wrong
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
    if (res.ok) {
      showAnswer(question, await res.json(), res.headers.get("X-Trace-ID") || "", performance.now() - started);
      setStatus("Done.", "done");
    } else {
      const error = await errorOf(res);       // 422, 502, 503, 504, ...: the server's message says what to do
      showFailure(question, error, performance.now() - started);
      setStatus(error.message, "error", error.trace_id);
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
