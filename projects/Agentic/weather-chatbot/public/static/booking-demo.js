/* An isolated, sandbox-only workflow. Provider text is always rendered as text, never as HTML. */
(() => {
  "use strict";
  const storageKey = "nimbus.booking-demo.v1";
  const controllers = new Map();
  const seenSeeds = new Set();
  const seededReceipts = new Map();
  let active = false;
  let latest = null;
  let storageAvailable = true;

  const phases = {
    flight_search: "Searching for Friday flights and a Sunday-evening return…",
    flight_verify: "Checking the selected flight’s availability and fare…",
    flight_prebook: "Preparing the simulated flight reservation…",
    flight_book: "Submitting the sandbox flight booking…",
    hotel_search: "Searching for a hotel near Zion in Springdale…",
    hotel_prebook: "Checking the hotel rate and availability…",
    hotel_book: "Submitting the sandbox hotel booking…",
  };
  const statuses = {
    idle: ["Waiting", "idle"],
    working: ["Working", "idle"],
    ready: ["Ready", "idle"],
    confirmed: ["Sandbox confirmed", "good"],
    pending: ["Pending confirmation", "warn"],
    failed: ["Could not complete", "bad"],
    unknown: ["Status unknown", "warn"],
    unavailable: ["No matching option", "warn"],
  };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function validReceipt(value) {
    return value && typeof value === "object" && typeof value.token === "string"
      && value.token.length > 0 && value.token.length < 250000
      && (!value.view || typeof value.view === "object");
  }

  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    if (validReceipt(stored)) {
      latest = stored;
      if (typeof stored.originSeed === "string") seededReceipts.set(stored.originSeed, stored);
    }
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

  function dateLabel(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return "";
    const date = new Date(`${value}T12:00:00Z`);
    if (!Number.isFinite(date.getTime())) return "";
    return new Intl.DateTimeFormat("en-US", {
      weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
    }).format(date);
  }

  function card(kind, data = {}) {
    const section = element("article", "booking-demo-card");
    const heading = element("div", "booking-demo-card-top");
    heading.append(element("span", "booking-demo-card-kind", kind === "flight" ? "Round-trip flight" : "Hotel stay"));
    const [label, tone] = statuses[data.status] || ["Status unknown", "warn"];
    const status = element("span", "booking-demo-state", label);
    status.dataset.tone = tone;
    heading.append(status);
    section.append(heading);
    section.append(element("h3", "", data.title || (kind === "flight" ? "DFW ⇄ LAX" : "Springdale · near Zion")));
    if (Array.isArray(data.details) && data.details.length) {
      const details = element("ul");
      for (const detail of data.details.slice(0, 12)) details.append(element("li", "", detail));
      section.append(details);
    }
    if (data.price !== undefined && data.price !== null && data.price !== "") {
      const price = element("p", "booking-demo-price", `${data.currency || "USD"} ${data.price}`);
      price.append(element("span", "", "sandbox quote"));
      section.append(price);
    }
    if (data.message) section.append(element("p", "", data.message));
    if (data.reference || data.booking_id) {
      const refs = element("dl", "booking-demo-reference");
      if (data.reference) {
        refs.append(element("dt", "", "Booking reference"), element("dd", "", data.reference));
      }
      if (data.booking_id && data.booking_id !== data.reference) {
        refs.append(element("dt", "", "Booking ID"), element("dd", "", data.booking_id));
      }
      section.append(refs);
    }
    return section;
  }

  function statusText(controller, text, error = false) {
    const node = controller.panel.querySelector("[data-demo-status]");
    node.textContent = text;
    node.dataset.error = String(error);
  }

  function controls(controller) {
    const { panel, receipt } = controller;
    const view = receipt?.view;
    const resume = panel.querySelector("[data-demo-resume]");
    const refresh = panel.querySelector("[data-demo-refresh]");
    resume.hidden = !receipt || Boolean(view?.complete) || Boolean(receipt?.inFlight);
    refresh.hidden = !receipt;
    for (const button of panel.querySelectorAll(".booking-demo-actions button")) button.disabled = active;
    const storage = panel.querySelector("[data-demo-storage]");
    const notes = [];
    if (!storageAvailable) notes.push("This browser cannot save the demo receipt. Keep this page open to see results.");
    if (view?.volatile) notes.push("This demo receipt may expire when the server restarts.");
    storage.hidden = notes.length === 0;
    storage.textContent = notes.join(" ");
    panel.setAttribute("aria-busy", String(active && controller.running));
  }

  function render(controller) {
    const view = controller.receipt?.view || {};
    const route = controller.panel.querySelector("[data-demo-route]");
    if (route) route.textContent = view.flight_destination
      ? `DFW ⇄ ${view.flight_destination}` : view.flight?.title || "DFW ⇄ LAX";
    const dates = [dateLabel(view.checkin), dateLabel(view.checkout)];
    if (dates.every(Boolean)) {
      controller.panel.querySelector("[data-demo-dates]").textContent = `${dates[0]} → ${dates[1]} · 2 nights`;
    }
    const cards = controller.panel.querySelector("[data-demo-cards]");
    cards.replaceChildren(card("flight", view.flight || { status: "idle" }), card("hotel", view.hotel || { status: "idle" }));
    const list = controller.panel.querySelector("[data-demo-events]");
    list.replaceChildren();
    for (const event of (Array.isArray(view.events) ? view.events : []).slice(-16)) {
      const outcome = statuses[event.status]?.[0] || String(event.status || "").replaceAll("_", " ");
      list.append(element("li", "", `${event.label || "Step"}${outcome ? ` · ${outcome}` : ""}`));
    }
    controller.panel.querySelector("[data-demo-progress]").hidden = list.childElementCount === 0;
    controls(controller);
  }

  function update(controller, receipt) {
    if (controller.seed) {
      receipt = { ...receipt, originSeed: controller.seed };
      seededReceipts.set(controller.seed, receipt);
    }
    controller.receipt = receipt;
    remember(receipt);
    render(controller);
    // The standalone page may host a second panel in an embedding; only synchronize the same demo or page view.
    for (const other of controllers.values()) {
      if (other === controller) continue;
      if (!other.panel.dataset.autostart || (controller.seed && other.seed === controller.seed)
        || (receipt.view?.id && other.receipt?.view?.id === receipt.view.id)) {
        other.receipt = receipt;
        render(other);
      }
    }
  }

  async function post(path, values) {
    const response = await fetch(path, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      body: new URLSearchParams(values), signal: AbortSignal.timeout(105000),
    });
    if (!response.ok) {
      if (response.status === 409) {
        const failure = await response.json().catch(() => ({}));
        if (failure.code === "route_changed") {
          throw new Error("The demo now uses LAX. Refresh older bookings only; start a new demo for DFW–LAX.");
        }
      }
      const error = new Error(response.status === 429
        ? "The sandbox is busy. Wait a minute, then refresh the booking status."
        : response.status === 400 || response.status === 403 || response.status === 410
          ? "This demo receipt is invalid or expired. Existing reservations have not been cancelled."
          : "The sandbox request did not finish. Refresh the booking status before continuing.");
      throw error;
    }
    const result = await response.json();
    if (!validReceipt(result) || !result.view) throw new Error("The sandbox response could not be read. Refresh its status.");
    return { token: result.token, view: result.view, inFlight: false };
  }

  function completionText(view) {
    if ([view.flight?.status, view.hotel?.status].includes("unknown")) {
      return "A booking’s final status is unknown. Refresh status; do not start a replacement booking yet.";
    }
    if ([view.flight?.status, view.hotel?.status].includes("pending")) {
      return "Sandbox requests finished. A booking is still pending confirmation; refresh to check again.";
    }
    return "Sandbox workflow finished. Check each card’s status above; only confirmed cards represent confirmed tests.";
  }

  async function run(controller, action) {
    if (active) {
      statusText(controller, "Another sandbox demo is running in this page. You can continue this one when it finishes.");
      return;
    }
    if (action !== "start" && !controller.receipt) return;
    active = true;
    controller.running = true;
    for (const item of controllers.values()) controls(item);
    try {
      if (action === "start") {
        statusText(controller, "Preparing a new sandbox demo…");
        update(controller, await post("/api/booking-demo/start", { action: "start" }));
      }
      if (action === "recover") {
        statusText(controller, "Checking the existing booking status. No replacement booking is being submitted…");
        update(controller, await post("/api/booking-demo/advance", {
          token: controller.receipt.token, action: "recover",
        }));
        statusText(controller, controller.receipt.view.complete
          ? completionText(controller.receipt.view)
          : "Status checked. Choose Resume demo to continue the remaining steps.");
        return;
      }
      for (let count = 0; count < 12 && !controller.receipt.view?.complete; count += 1) {
        const receipt = { ...controller.receipt, inFlight: true };
        update(controller, receipt);
        statusText(controller, phases[receipt.view?.next_phase] || "Contacting the sandbox…");
        update(controller, await post("/api/booking-demo/advance", { token: receipt.token, action: "advance" }));
      }
      statusText(controller, controller.receipt.view?.complete
        ? completionText(controller.receipt.view)
        : "The demo paused at its step limit. Refresh its status before continuing.");
    } catch (error) {
      // Preserve the last signed receipt. In particular, never replay a booking automatically after a timeout.
      statusText(controller, error instanceof Error && error.name === "Error"
        ? error.message
        : "The connection was interrupted. Refresh booking status before continuing; the request may have succeeded.", true);
    } finally {
      active = false;
      controller.running = false;
      for (const item of controllers.values()) controls(item);
    }
  }

  function initialize(panel) {
    if (controllers.has(panel)) return;
    const seed = panel.dataset.seed;
    const automatic = panel.dataset.autostart === "true" && Boolean(seed);
    const previous = automatic ? seededReceipts.get(seed) : null;
    const controller = { panel, seed: automatic ? seed : null, receipt: automatic ? previous || {
      token: seed,
      view: { checkin: panel.dataset.checkin, checkout: panel.dataset.checkout, next_phase: "flight_search" },
      inFlight: false,
      originSeed: seed,
    } : latest, running: false };
    controllers.set(panel, controller);
    render(controller);
    panel.querySelector("[data-demo-start]")?.addEventListener("click", () => run(controller, "start"));
    panel.querySelector("[data-demo-resume]").addEventListener("click", () => run(controller, "advance"));
    panel.querySelector("[data-demo-refresh]").addEventListener("click", () => run(controller, "recover"));
    if (automatic && !previous && !seenSeeds.has(seed)) {
      seenSeeds.add(seed);
      seededReceipts.set(seed, controller.receipt);
      remember(controller.receipt);
      run(controller, "advance");
    } else if (controller.receipt) {
      statusText(controller, "Showing the saved result from this tab. Refresh booking status to get the latest provider response.");
    }
  }

  function discover() {
    for (const panel of document.querySelectorAll("[data-booking-demo]")) initialize(panel);
    for (const [panel, controller] of controllers) {
      if (!panel.isConnected && !controller.running) controllers.delete(panel);
    }
  }

  discover();
  new MutationObserver(discover).observe(document.body, { childList: true, subtree: true });
})();
