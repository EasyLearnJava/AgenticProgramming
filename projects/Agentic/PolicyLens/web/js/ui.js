// Escape every document, question and answer before placing it in HTML.
// We deliberately avoid rendering arbitrary Markdown or HTML from source files.
export const $ = (selector) => document.querySelector(selector);
export const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));
export const percent = (value) => value == null ? "—" : `${(value * 100).toFixed(0)}%`;
export const date = (value) => value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "Not built";
export const safeUrl = (value) => {
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? escape(url.href) : ""; }
  catch { return ""; }
};

let toastTimer;
export function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast${error ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.add("hidden"), error ? 8500 : 4500);
}

export function metric(label, value, description) {
  return `<div class="metric-card"><span>${escape(label)}</span><strong>${escape(value)}</strong><small>${escape(description)}</small></div>`;
}

export function openDialog(title, subtitle, html) {
  $("#dialog-title").textContent = title;
  $("#dialog-subtitle").textContent = subtitle;
  $("#dialog-content").innerHTML = html;
  const dialog = $("#source-dialog");
  if (!dialog.open) dialog.showModal();
}

export function initDialog() {
  const dialog = $("#source-dialog");
  $("#close-dialog").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
}

