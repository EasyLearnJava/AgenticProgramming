/* htmx submits each inline planner to its own chat turn. Keep its progress, errors and focus local to that turn. */
(() => {
  "use strict";
  const messages = document.getElementById("messages");

  function onPlanner(type, handler) {
    messages.addEventListener(type, (event) => {
      const form = event.target;
      if (form.matches("form.trip-form:not(.brief-action)")) {
        handler(form, event);
      }
    });
  }

  function setStatus(form, text) {
    form.querySelector("[data-trip-status]").textContent = text;
  }

  onPlanner("htmx:before:request", (form) => {
    setStatus(form, "Building your trip plan…");
  });

  // An edge error or a full page from an older deployment must never replace part of the conversation.
  onPlanner("htmx:before:response", (form, event) => {
    const response = event.detail.ctx.response;
    if (response.headers.get("x-nimbus-trip") !== "fragment") {
      event.preventDefault();
      setStatus(form, response.status === 429
        ? "Trip planning is busy. Please wait and try again."
        : "Your plan could not be loaded. Your trip details are here to try again.");
    }
  });

  onPlanner("htmx:error", (form) => {
    setStatus(form, "Could not reach Nimbus. Check your connection and try again.");
  });

  onPlanner("htmx:after:swap", (form) => {
    setStatus(form, "");
    const editor = form.closest(".trip-editor");
    const result = editor.parentElement.querySelector(".trip-inline-result");
    const heading = result.querySelector("[data-trip-result-heading]");
    const moveFocus = editor.contains(document.activeElement) || document.activeElement === document.body;
    editor.open = !heading;
    if (moveFocus) {
      (heading || result.querySelector("[data-trip-error]"))?.focus();
    }
  });

  messages.addEventListener("change", (event) => {
    const mode = event.target;
    if (!mode.matches("[data-quote-mode]")) return;
    const hotelsOnly = mode.value === "true";
    const flightFields = mode.form.querySelector("[data-flight-fields]");
    flightFields.hidden = hotelsOnly;
    flightFields.disabled = hotelsOnly;
    const arrival = mode.form.elements.arrival;
    arrival.value = hotelsOnly ? arrival.dataset.hotelDate : arrival.dataset.flightDate;
    mode.form.querySelector("button[type=submit]").textContent = hotelsOnly ? "Search hotels" : "Search flights and hotels";
  });

  // A successful briefing replaces the form. Restore keyboard focus only if the visitor stayed in this card.
  messages.addEventListener("htmx:after:swap", (event) => {
    if (event.target.matches(".trip-card") && document.activeElement === document.body) {
      event.target.querySelector("[data-brief-heading]")?.focus();
    }
  });

  function onBriefing(type, handler) {
    messages.addEventListener(type, (event) => {
      if (event.target.matches("form.brief-action")) handler(event.target, event);
    });
  }
  onBriefing("htmx:before:request", (form) => {
    form.querySelector('[role="status"]').textContent = "Checking park conditions…";
  });
  onBriefing("htmx:before:response", (form, event) => {
    const response = event.detail.ctx.response;
    if (response.headers.get("x-nimbus-briefing") !== "fragment") {
      event.preventDefault();
      form.querySelector('[role="status"]').textContent = response.status === 429
        ? "Trip checks are busy. Try again shortly." : "Check the selected park and dates, then try again.";
    }
  });
  onBriefing("htmx:error", (form) => {
    form.querySelector('[role="status"]').textContent = "Could not reach Nimbus. Try again.";
  });
  // Cancel outstanding lookups before New chat removes their destination elements.
  document.getElementById("new-chat").addEventListener("click", () => {
    for (const form of messages.querySelectorAll(".trip-form.htmx-request, .brief-action.htmx-request")) {
      htmx.trigger(form, "htmx:abort");
    }
  }, { capture: true });
})();
