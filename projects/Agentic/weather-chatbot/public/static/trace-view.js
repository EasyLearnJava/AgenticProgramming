/* Local interaction with projected metadata only; no network requests, HTML injection or private payloads. */
(() => {
  "use strict";
  const explorer = document.querySelector("[data-trace-explorer]");
  if (!explorer) return;
  const rows = Array.from(explorer.querySelectorAll("[data-trace-row]"));
  if (!rows.length) return;
  const byKey = new Map(rows.map((row) => [row.dataset.traceRow, row]));
  const collapsed = new Set();
  const filters = Array.from(explorer.querySelectorAll("[data-trace-filter]"));
  const search = explorer.querySelector("#trace-search");
  const count = explorer.querySelector("[data-trace-count]");
  const empty = explorer.querySelector("[data-trace-empty]");
  const expand = explorer.querySelector("[data-trace-expand]");
  const collapse = explorer.querySelector("[data-trace-collapse]");
  let activeFilter = "all";
  let selectedKey = rows[0].dataset.traceRow;
  const ancestors = (row) => (row.dataset.ancestors || "").split(",").filter(Boolean);
  const setText = (selector, text) => {
    const target = explorer.querySelector(selector);
    if (target) target.textContent = text;
  };

  function select(row, announce = true) {
    selectedKey = row.dataset.traceRow;
    rows.forEach((other) => {
      const selected = other === row;
      other.dataset.selected = String(selected);
      other.querySelector("[data-trace-select]").setAttribute("aria-pressed", String(selected));
    });
    setText("[data-trace-detail-label]", row.dataset.label);
    setText("[data-trace-detail-kind]", row.dataset.callKind);
    setText("[data-trace-detail-duration]", row.dataset.duration);
    setText("[data-trace-detail-start]", row.dataset.start);
    for (const field of ["outcome", "cacheReason", "score", "threshold", "retrievalMode", "retrievalProvider",
      "retrievalCandidates", "retrievalSelected", "retrievalSeasonSource"]) {
      const value = row.dataset[field] || "";
      setText(`[data-trace-detail-${field}]`, value);
      explorer.querySelector(`[data-trace-field="${field}"]`).hidden = !value;
    }
    explorer.querySelector("[data-trace-score-note]").hidden = !row.dataset.threshold;
    const parent = byKey.get(row.dataset.parent);
    const parentLabel = parent ? parent.dataset.label :
      (["agent", "memory", "retrieval"].includes(row.dataset.kind) ? "None (trace root)" : "Not available in this view");
    setText("[data-trace-detail-parent]", parentLabel);
    const status = explorer.querySelector("[data-trace-detail-status]");
    status.textContent = row.dataset.callStatus;
    status.dataset.status = row.dataset.status;
    const error = explorer.querySelector("[data-trace-detail-error]");
    error.textContent = row.dataset.error || "";
    error.hidden = !row.dataset.error;
    if (announce) setText("[data-trace-selection-note]", `Selected ${row.dataset.label}, ${row.dataset.callStatus}.`);
  }

  function refresh() {
    const query = search.value.trim().toLocaleLowerCase();
    const filtering = activeFilter !== "all" || Boolean(query);
    const matches = new Set(rows.filter((row) => {
      const kindMatches = activeFilter === "all" || row.dataset.kind === activeFilter ||
        (activeFilter === "failed" && row.dataset.status === "failed");
      return kindMatches && row.dataset.label.toLocaleLowerCase().includes(query);
    }).map((row) => row.dataset.traceRow));
    const visibleKeys = new Set(matches);
    rows.forEach((row) => {
      if (matches.has(row.dataset.traceRow)) ancestors(row).forEach((key) => visibleKeys.add(key));
    });
    rows.forEach((row) => {
      const key = row.dataset.traceRow;
      row.hidden = !visibleKeys.has(key) || (!filtering && ancestors(row).some((key) => collapsed.has(key)));
      row.dataset.context = String(filtering && !matches.has(key));
      const toggle = row.querySelector("[data-trace-toggle]");
      if (toggle) {
        const expanded = filtering || !collapsed.has(key);
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${row.dataset.label}`);
        toggle.disabled = filtering;
        toggle.title = filtering ? "Clear filters to collapse calls" : "";
      }
    });
    const visible = rows.filter((row) => !row.hidden);
    count.textContent = filtering ? `${matches.size} matching ${matches.size === 1 ? "call" : "calls"}` :
      `${visible.length} of ${rows.length} calls shown`;
    empty.hidden = matches.size !== 0;
    expand.disabled = filtering;
    collapse.disabled = filtering;
    explorer.querySelector("[data-trace-inspector]").hidden = matches.size === 0;
    const selected = byKey.get(selectedKey);
    if (visible.length && (!selected || selected.hidden)) select(visible[0], false);
  }

  explorer.querySelectorAll("[data-trace-controls], [data-trace-toggle]").forEach((item) => { item.hidden = false; });
  rows.forEach((row) => {
    const button = row.querySelector("[data-trace-select]");
    button.disabled = false;
    button.addEventListener("click", () => select(row));
    const toggle = row.querySelector("[data-trace-toggle]");
    if (toggle) toggle.addEventListener("click", () => {
      const key = row.dataset.traceRow;
      if (collapsed.has(key)) collapsed.delete(key);
      else collapsed.add(key);
      refresh();
    });
  });
  filters.forEach((button) => button.addEventListener("click", () => {
    activeFilter = button.dataset.traceFilter;
    filters.forEach((filter) => filter.setAttribute("aria-pressed", String(filter === button)));
    refresh();
  }));
  search.addEventListener("input", refresh);
  expand.addEventListener("click", () => { collapsed.clear(); refresh(); });
  collapse.addEventListener("click", () => {
    rows.forEach((row) => { if (row.querySelector("[data-trace-toggle]")) collapsed.add(row.dataset.traceRow); });
    refresh();
  });
  explorer.querySelector("[data-trace-clear]").addEventListener("click", () => {
    activeFilter = "all";
    search.value = "";
    filters.forEach((filter) => filter.setAttribute("aria-pressed", String(filter.dataset.traceFilter === "all")));
    refresh();
    search.focus();
  });
  select(rows[0], false);
  refresh();
})();
