import { request } from "./api.js";
import { $, date, escape, metric, openDialog, safeUrl, toast } from "./ui.js";

export function renderKnowledge(status) {
  $("#knowledge-metrics").innerHTML = metric("DOCUMENTS", status.documents.length, "Public corpus + your uploads") +
    metric("INDEXED CHUNKS", status.chunk_count, `${status.chunk_size} tokens · ${status.chunk_overlap} overlap`) +
    metric("RETRIEVAL DEPTH", `${status.top_k} chunks`, "Top evidence passed to answering") +
    metric("LAST BUILT", date(status.built_at).replace(/,? \d{4}/, ""), status.needs_rebuild ? "Rebuild required" : "Index is up to date");
  $("#collection-date").textContent = `Freshness target: ${status.freshness_days} days`;
  $("#document-list").innerHTML = status.documents.map((doc) => `<div class="document-row"><span class="document-file-icon" aria-hidden="true">▤</span><div><button class="document-name" data-source="${escape(doc.source_id)}">${escape(doc.title)}</button><span class="document-meta">${escape(doc.category)} · ${escape(doc.kind)} · ${date(doc.fetched_at)}</span></div><div class="document-spacer"><span class="document-chunks">${doc.chunks} chunks</span><span class="badge ${!doc.indexed || status.needs_rebuild ? "pending" : ""}">${!doc.indexed ? "Pending index" : status.needs_rebuild ? "Rebuild needed" : "Indexed"}</span>${doc.category === "Uploaded" ? `<button class="button secondary" data-remove="${escape(doc.source_id)}">Remove</button>` : ""}<button class="icon-button" data-source="${escape(doc.source_id)}" aria-label="Read ${escape(doc.title)}">↗</button></div></div>`).join("") || '<div class="empty-state"><p>Add a document to get started.</p></div>';
}

export function initKnowledge(refreshStatus) {
  $("#rebuild-button").addEventListener("click", async () => {
    const button = $("#rebuild-button");
    button.disabled = true;
    button.textContent = "Building index…";
    try {
      const result = await request("/index", { method: "POST" });
      await refreshStatus();
      toast(`Index ready: ${result.documents} documents, ${result.chunks} chunks.`);
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.textContent = "↻ Rebuild index"; }
  });

  async function upload(file) {
    if (!file) return;
    const zone = $("#upload-zone");
    if (zone.dataset.busy) return;
    zone.dataset.busy = "true";
    const form = new FormData();
    form.append("file", file);
    toast(`Reading ${file.name}…`);
    try {
      const result = await request("/documents", { method: "POST", body: form });
      await refreshStatus();
      toast(result.message);
    } catch (error) { toast(error.message, true); }
    finally { delete zone.dataset.busy; $("#file-input").value = ""; }
  }
  $("#file-input").addEventListener("change", (event) => upload(event.target.files[0]));
  const zone = $("#upload-zone");
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("dragging"); }));
  zone.addEventListener("drop", (event) => upload(event.dataTransfer.files[0]));

  $("#document-list").addEventListener("click", async (event) => {
    const remove = event.target.closest("[data-remove]");
    if (remove) {
      try {
        const result = await request(`/documents/${encodeURIComponent(remove.dataset.remove)}`, {method:"DELETE"});
        await refreshStatus();
        toast(result.message);
      } catch (error) { toast(error.message, true); }
      return;
    }
    const button = event.target.closest("[data-source]");
    if (!button) return;
    try {
      const doc = await request(`/documents/${encodeURIComponent(button.dataset.source)}`);
      const url = safeUrl(doc.url);
      openDialog(doc.title, `Snapshot: ${date(doc.fetched_at)}`, (url ? `<a class="button secondary" href="${url}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>` : "") + `<pre>${escape(doc.text)}</pre>`);
    } catch (error) { toast(error.message, true); }
  });

  $("#removed-documents").addEventListener("click", async () => {
    try {
      const docs = await request("/documents/removed");
      openDialog("Removed documents", "Restore an upload, then rebuild the index.", docs.length
        ? docs.map((doc) => `<p>${escape(doc.title)} <button class="button secondary" data-restore="${escape(doc.source_id)}">Restore</button></p>`).join("")
        : "<p>No removed documents.</p>");
    } catch (error) { toast(error.message, true); }
  });
  $("#dialog-content").addEventListener("click", async (event) => {
    const restore = event.target.closest("[data-restore]");
    if (!restore) return;
    try {
      const result = await request(`/documents/${encodeURIComponent(restore.dataset.restore)}/restore`, {method:"POST"});
      await refreshStatus();
      $("#source-dialog").close();
      toast(result.message);
    } catch (error) { toast(error.message, true); }
  });
}

