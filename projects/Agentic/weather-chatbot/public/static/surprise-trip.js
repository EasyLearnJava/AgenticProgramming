/* This exact surprise-trip experience owns its planner, approval and receipts; regular chat stays independent. */
(() => {
  "use strict";
  const storageKey = "nimbus.surprise-trip.v1";
  const controllers = new Map();
  let latest = null;
  let active = false;
  let storageAvailable = true;
  let typedYesController = null;
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const stopPhases = new Set(["awaiting_confirmation", "done", "failed", "cancelled", "expired"]);
  const phaseWords = {
    search: "Searching flights and hotels independently. Nothing is booked…",
    flight_search: "Searching DFW–Las Vegas flights for your dates and party…",
    flight_verify: "Verifying the flight fare and itinerary…",
    flight_prebook: "Preparing the flight quote with synthetic travelers. Nothing is booked…",
    hotel_search: "Searching for a hotel near Grand Canyon’s South Rim…",
    hotel_prebook: "Checking the full hotel stay and mandatory fees. Nothing is booked…",
    flight_refresh: "Rechecking the approved flight quote…",
    hotel_refresh: "Rechecking the approved hotel quote and combined total…",
    flight_book: "Submitting the approved sandbox flight booking…",
    hotel_book: "Submitting the approved sandbox hotel booking…",
  };
  const statusWords = {
    idle: ["Not searched yet", "idle"], skipped: ["Not searched", "idle"],
    ready: ["Quote ready", "idle"], quoted: ["Quote ready", "idle"],
    working: ["Working", "idle"], confirmed: ["Sandbox confirmed", "good"],
    pending: ["Pending confirmation", "warn"], unknown: ["Status unknown", "warn"],
    unavailable: ["Unavailable", "warn"], failed: ["Could not complete", "bad"],
    cancelled: ["Declined", "idle"], expired: ["Quote expired", "warn"],
  };

  function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined) result.textContent = String(text);
    return result;
  }

  function validReceipt(value) {
    return value && typeof value === "object" && typeof value.token === "string"
      && value.token.length > 0 && value.token.length < 400000
      && value.view && typeof value.view === "object";
  }

  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    if (validReceipt(saved)) latest = saved;
  } catch {
    storageAvailable = false;
  }

  function remember(receipt) {
    latest = receipt;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(receipt));
    } catch {
      storageAvailable = false;
    }
  }

  function formatDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return "";
    const date = new Date(`${value}T12:00:00Z`);
    return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat("en-US", {
      month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
    }).format(date) : "";
  }

  function amount(view) {
    return Number.isSafeInteger(view?.total_cents) && view.total_cents >= 0 ? view.total_cents : null;
  }

  function formMatches(controller) {
    const view = controller.receipt?.view;
    if (!view) return false;
    const fields = controller.form.elements;
    return fields.checkin.value === view.checkin && fields.checkout.value === view.checkout
      && Number(fields.adults.value) === Number(view.adults);
  }

  function quoteCurrent(controller) {
    const view = controller.receipt?.view;
    return view?.phase === "awaiting_confirmation" && amount(view) !== null
      && Number.isFinite(view.quote_expires) && view.quote_expires * 1000 > Date.now()
      && formMatches(controller) && !controller.receipt.inFlight;
  }

  function setStatus(controller, message, error = false) {
    const line = controller.panel.querySelector("[data-surprise-status]");
    line.textContent = message;
    line.dataset.error = String(error);
  }

  function card(kind, product = {}, phase) {
    const result = node("article", "surprise-trip-card");
    const top = node("div", "surprise-trip-card-top");
    top.append(node("span", "surprise-trip-card-kind", kind === "flight" ? "Round-trip flight" : "Hotel stay"));
    const notSearched = product.status === "idle" || product.status === "skipped";
    const stopped = stopPhases.has(phase);
    const [word, tone] = notSearched && stopped ? ["Not searched", "idle"]
      : statusWords[product.status] || ["Status unknown", "warn"];
    const status = node("span", "surprise-trip-state", word);
    status.dataset.tone = tone;
    top.append(status);
    result.append(top, node("h3", "", product.title || (kind === "flight" ? "DFW ↔ LAS" : "Grand Canyon South Rim")));
    if (Array.isArray(product.details) && product.details.length) {
      const details = node("ul");
      for (const item of product.details.slice(0, 14)) details.append(node("li", "", item));
      result.append(details);
    }
    if (product.price !== undefined && product.price !== null && product.price !== "") {
      result.append(node("p", "surprise-trip-card-price", `${product.currency || "USD"} ${product.price}`));
      result.append(node("p", "surprise-trip-card-price-label", kind === "flight"
        ? "All selected travelers · round trip" : "All rooms and nights · known mandatory fees included"));
    }
    const message = product.message || (notSearched
      ? stopped ? `This ${kind} search did not run before the trip workflow stopped.`
        : `This ${kind} search has not started yet.`
      : "");
    if (message) result.append(node("p", "", message));
    if (product.reference || product.booking_id) {
      const references = node("dl", "surprise-trip-reference");
      if (product.reference) references.append(node("dt", "", "Booking reference"), node("dd", "", product.reference));
      if (product.booking_id && product.booking_id !== product.reference) {
        references.append(node("dt", "", "Booking ID"), node("dd", "", product.booking_id));
      }
      result.append(references);
    }
    return result;
  }

  function updateControls(controller) {
    const { panel, receipt, form } = controller;
    const view = receipt?.view;
    const awaiting = view?.phase === "awaiting_confirmation";
    const valid = quoteCurrent(controller);
    const approval = panel.querySelector("[data-surprise-approval]");
    approval.hidden = !awaiting;
    const confirm = panel.querySelector("[data-surprise-confirm]");
    confirm.disabled = active || !valid;
    confirm.hidden = awaiting && !valid && !active;
    panel.querySelector("[data-surprise-cancel]").disabled = active;
    const expires = panel.querySelector("[data-surprise-expiry]");
    if (awaiting) {
      const remaining = Math.max(0, Math.ceil((Number(view.quote_expires) * 1000 - Date.now()) / 1000));
      const text = !formMatches(controller)
        ? "Dates or traveler count changed. Find a new quote before approving."
        : !remaining || !Number.isFinite(remaining)
          ? "This quote expired. Find a new quote before approving."
          : receipt.inFlight
            ? "A request was interrupted. Refresh status before deciding what to do next."
            : `Quote expires in ${Math.floor(remaining / 60)}m ${remaining % 60}s. Prices are rechecked before booking.`;
      if (expires.textContent !== text) expires.textContent = text;
    }
    const resume = panel.querySelector("[data-surprise-resume]");
    resume.hidden = !receipt || stopPhases.has(view?.phase) || Boolean(receipt.inFlight);
    resume.disabled = active;
    const refresh = panel.querySelector("[data-surprise-refresh]");
    const approved = Number.isSafeInteger(view?.approved_cents) && view.approved_cents >= 0;
    refresh.hidden = !receipt || (!approved && !receipt.inFlight);
    refresh.disabled = active;
    for (const control of form.querySelectorAll("input, button")) control.disabled = active;
    const adults = Number(form.elements.adults.value);
    const rooms = Math.ceil(adults / 2);
    panel.querySelector("[data-surprise-rooms]").textContent = Number.isInteger(adults) && adults >= 1 && adults <= 6
      ? `${rooms} room${rooms === 1 ? "" : "s"} · at most 2 adults per room · stays of 1–14 nights.`
      : "Choose 1–6 adults. We allocate at most 2 adults per room.";
    const storage = panel.querySelector("[data-surprise-storage]");
    const notices = [];
    if (!storageAvailable) notices.push("This browser cannot save receipts. Keep this page open to see the results.");
    if (view?.volatile) notices.push("This server’s demo receipt can expire after a restart.");
    storage.hidden = notices.length === 0;
    storage.textContent = notices.join(" ");
    panel.setAttribute("aria-busy", String(active && controller.running));
  }

  function render(controller) {
    const { panel, receipt } = controller;
    const view = receipt?.view;
    panel.querySelector("[data-surprise-results]").hidden = !view;
    if (view) {
      const dates = [formatDate(view.checkin), formatDate(view.checkout)];
      panel.querySelector("[data-surprise-itinerary]").textContent = dates.every(Boolean)
        ? `${dates[0]} → ${dates[1]} · ${view.adults} adult${view.adults === 1 ? "" : "s"} · ${view.rooms} room${view.rooms === 1 ? "" : "s"}`
        : "Your selected trip";
      panel.querySelector("[data-surprise-cards]").replaceChildren(card("flight", view.flight, view.phase), card("hotel", view.hotel, view.phase));
      const total = amount(view);
      const totalSection = panel.querySelector("[data-surprise-total]");
      totalSection.hidden = total === null;
      if (total !== null) {
        const over = total > 80000;
        totalSection.dataset.overBudget = String(over);
        panel.querySelector("[data-surprise-amount]").textContent = money.format(total / 100);
        const approved = view.approved_cents === total;
        panel.querySelector("[data-surprise-budget]").textContent = approved
          ? `You approved this total${over ? ", including the amount above $800" : ""}. Check each booking’s status.`
          : over
            ? `${money.format((total - 80000) / 100)} above the $800 budget. Your explicit approval is required.`
            : "Within the $800 budget. Your explicit approval is still required.";
        panel.querySelector("[data-surprise-confirm-copy]").textContent = over
          ? `This combined quote is ${money.format(total / 100)}, above $800. Say yes only if you approve this total for both simulated bookings.`
          : `Approve ${money.format(total / 100)} for both simulated bookings? Neither will be booked before you say yes.`;
      }
      const events = panel.querySelector("[data-surprise-events]");
      events.replaceChildren();
      for (const event of (Array.isArray(view.events) ? view.events : []).slice(-24)) {
        const status = statusWords[event.status]?.[0] || String(event.status || "").replaceAll("_", " ");
        const message = typeof event.message === "string" ? event.message.trim() : "";
        events.append(node("li", "", `${event.label || "Step"}${status ? ` · ${status}` : ""}${message ? ` — ${message}` : ""}`));
      }
      panel.querySelector("[data-surprise-progress]").hidden = events.childElementCount === 0;
    }
    updateControls(controller);
  }

  function update(controller, receipt) {
    controller.receipt = receipt;
    remember(receipt);
    render(controller);
    for (const other of controllers.values()) {
      if (other !== controller && receipt.view?.id && other.receipt?.view?.id === receipt.view.id) {
        other.receipt = receipt;
        render(other);
      }
    }
  }

  async function post(path, fields) {
    const response = await fetch(path, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      body: new URLSearchParams(fields), signal: AbortSignal.timeout(105000),
    });
    if (!response.ok) {
      const error = new Error(response.status === 429
        ? "The sandbox is busy. Wait a minute before continuing."
        : response.status === 410
          ? "This receipt expired or the server restarted. Saved cards are not a current confirmation."
          : response.status === 400 || response.status === 403 || response.status === 409
            ? "The request could not be accepted. Check the dates, party and current quote before continuing."
            : "The sandbox request did not finish. Refresh the existing attempt before continuing.");
      throw error;
    }
    const result = await response.json();
    if (!validReceipt(result)) throw new Error("The response could not be read. Refresh the existing attempt before continuing.");
    return { token: result.token, view: result.view, inFlight: false };
  }

  function completionText(view) {
    if (view.message) return String(view.message);
    if (view.phase === "awaiting_confirmation") return "Your quote is ready. Nothing is booked. Review the total and choose Yes or No.";
    if (view.phase === "cancelled") return "Quote declined. No new bookings will be submitted.";
    if (view.phase === "expired") return "This quote expired. Find a new quote to review before approving.";
    if ([view.flight?.status, view.hotel?.status].includes("unknown")) {
      return "A booking’s outcome is unknown. Refresh the existing attempt; do not start a replacement booking.";
    }
    if ([view.flight?.status, view.hotel?.status].includes("pending")) {
      return "A simulated reservation is pending confirmation. Check both cards and refresh its status later.";
    }
    if (view.phase === "failed") return "This trip could not be completed. Check each card; a partial booking is not a completed trip.";
    return "Check both cards for the final sandbox status. Only confirmed cards represent confirmed test reservations.";
  }

  async function drive(controller) {
    for (let count = 0; count < 12; count += 1) {
      const phase = controller.receipt.view.phase;
      if (stopPhases.has(phase)) break;
      const receipt = { ...controller.receipt, inFlight: true };
      update(controller, receipt);
      setStatus(controller, phaseWords[phase] || "Preparing your sandbox trip…");
      update(controller, await post("/api/surprise-trip/advance", { token: receipt.token, action: "advance" }));
    }
    setStatus(controller, stopPhases.has(controller.receipt.view.phase)
      ? completionText(controller.receipt.view)
      : "The workflow paused. Refresh its status before continuing the remaining steps.");
  }

  async function run(controller, action) {
    if (active) return;
    if (action === "confirm" && !quoteCurrent(controller)) {
      setStatus(controller, "This quote cannot be approved. Check its dates and expiry, or request a fresh quote.", true);
      return;
    }
    if (action !== "quote" && !controller.receipt) return;
    let fields;
    if (action === "quote") {
      if (!controller.form.reportValidity()) return;
      fields = new FormData(controller.form);
      const start = Date.parse(`${fields.get("checkin")}T12:00:00Z`);
      const end = Date.parse(`${fields.get("checkout")}T12:00:00Z`);
      const nights = (end - start) / 86400000;
      if (!Number.isInteger(nights) || nights < 1 || nights > 14) {
        setStatus(controller, "Choose a return date 1–14 nights after departure.", true);
        return;
      }
    }
    active = true;
    controller.running = true;
    for (const item of controllers.values()) updateControls(item);
    try {
      if (action === "quote") {
        setStatus(controller, "Preparing your dates and party. No booking will be submitted without approval…");
        update(controller, await post("/api/surprise-trip/start", Object.fromEntries(fields)));
        await drive(controller);
      } else {
        const receipt = { ...controller.receipt, inFlight: true };
        update(controller, receipt);
        setStatus(controller, action === "confirm" ? "Your approval was received. Rechecking prices before booking…"
          : action === "cancel" ? "Declining this quote…" : "Checking the existing attempt. No replacement reservation is being created…");
        update(controller, await post("/api/surprise-trip/advance", { token: receipt.token, action }));
        if (action === "confirm" || action === "advance") await drive(controller);
        else setStatus(controller, stopPhases.has(controller.receipt.view.phase)
          ? completionText(controller.receipt.view)
          : "Status checked. Choose Resume remaining steps to continue this same attempt.");
      }
    } catch (error) {
      setStatus(controller, error instanceof Error && error.name === "Error" ? error.message
        : "The connection was interrupted. The last attempt may have succeeded; refresh its status before continuing.", true);
    } finally {
      active = false;
      controller.running = false;
      for (const item of controllers.values()) updateControls(item);
    }
  }

  function initialize(panel) {
    if (controllers.has(panel)) return;
    const inChat = panel.dataset.surpriseChat === "true";
    const controller = { panel, form: panel.querySelector("[data-surprise-form]"), receipt: inChat ? null : latest, running: false };
    controllers.set(panel, controller);
    if (controller.receipt) {
      for (const field of ["checkin", "checkout", "adults"]) {
        if (controller.receipt.view[field] !== undefined) controller.form.elements[field].value = controller.receipt.view[field];
      }
      const savedMessage = controller.receipt.view.message ? `${controller.receipt.view.message} ` : "";
      setStatus(controller, `${savedMessage}Showing this tab’s saved result. No booking restarts automatically; refresh to check the provider’s latest status.`);
    }
    controller.form.addEventListener("submit", (event) => {
      event.preventDefault();
      event.stopPropagation();
      run(controller, "quote");
    });
    controller.form.addEventListener("input", () => updateControls(controller));
    panel.querySelector("[data-surprise-confirm]").addEventListener("click", () => run(controller, "confirm"));
    panel.querySelector("[data-surprise-cancel]").addEventListener("click", () => run(controller, "cancel"));
    panel.querySelector("[data-surprise-refresh]").addEventListener("click", () => run(controller, "recover"));
    panel.querySelector("[data-surprise-resume]").addEventListener("click", () => run(controller, "advance"));
    if (inChat) typedYesController = controller;
    render(controller);
  }

  function discover() {
    for (const panel of document.querySelectorAll("[data-surprise-trip]")) initialize(panel);
    for (const [panel, controller] of controllers) {
      if (!panel.isConnected && !controller.running) {
        controllers.delete(panel);
        if (typedYesController === controller) typedYesController = null;
      }
    }
  }

  // Capture only a yes belonging to the latest uninterrupted surprise request. All other chat submits pass through.
  document.addEventListener("submit", (event) => {
    if (event.target.id !== "chat-form") return;
    const question = document.getElementById("question");
    const controller = typedYesController;
    const users = document.querySelectorAll("#messages > .message-user");
    const lastQuestion = users.length ? users[users.length - 1].querySelector(".bubble")?.textContent.trim().toLowerCase() : "";
    if (question?.value.trim().toLowerCase() === "yes" && controller?.panel.isConnected
      && controller.receipt?.view.phase === "awaiting_confirmation" && lastQuestion === "book a surprise trip") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!active) {
        question.value = "";
        run(controller, "confirm");
      }
      return;
    }
    typedYesController = null;
  }, true);

  discover();
  new MutationObserver(discover).observe(document.body, { childList: true, subtree: true });
  setInterval(() => {
    for (const controller of controllers.values()) {
      if (controller.receipt?.view.phase === "awaiting_confirmation") updateControls(controller);
    }
  }, 1000);
})();
