/*
 * public/static/chat.js: what the chat needs beyond htmx. htmx posts each question and puts each event of the answer's
 * stream into the page (templates/chat.html); this script adds Stop, clears the box once an answer is under way, keeps
 * the focus and the newest message in view, and shows our own sentence when no answer can come from us. It only ever
 * puts text into the page (textContent), never HTML, and the sentences are the server's, from the conversation's
 * data-* attributes.
 */
(() => {
  "use strict";
  const form = document.getElementById("chat-form");
  if (!form) {
    return;
  }
  const messages = document.getElementById("messages");
  const box = document.getElementById("question");
  const send = document.getElementById("send");
  const stop = document.getElementById("stop");
  const errorTemplate = document.getElementById("chat-error-template");
  const historyField = document.getElementById("history");
  let isStopping = false;
  let hasStarted = false;

  /** Scrolls the conversation's newest message into view. */
  function showNewest() {
    messages.lastElementChild?.scrollIntoView({ block: "nearest" });
  }

  /** Marks each tool call still running in a message as stopped: the answer ended before the call did. */
  function stopChips(message) {
    for (const chip of message.querySelectorAll(".tool-chip-running")) {
      chip.classList.replace("tool-chip-running", "tool-chip-stopped");
      chip.querySelector(".tool-chip-mark").textContent = messages.dataset.chipStoppedMark;
      chip.querySelector(".tool-chip-word").textContent = messages.dataset.chipStoppedWord;
    }
  }

  /**
   * Ends an answer that never got its end with a note (Stopped, or cut off), its running tool calls marked stopped,
   * and marks it no longer busy.
   */
  function endWithNote(message, sentence) {
    const note = document.createElement("p");
    note.className = "message-note";
    note.textContent = sentence;
    message.querySelector(".bubble").append(note);
    stopChips(message);
    message.removeAttribute("aria-busy");
  }

  /** Adds Nimbus's message that's only an error, from the page's own template. */
  function showError(sentence) {
    const message = errorTemplate.content.firstElementChild.cloneNode(true);
    message.querySelector(".message-note").textContent = sentence;
    messages.append(message);
    showNewest();
  }

  // ① Stop: htmx aborts the request, and the answer ends on the page. On your computer the server hears the browser
  // go, and stops the answer too; on Vercel it can't (issue 32).
  stop.addEventListener("click", () => {
    isStopping = true;
    htmx.trigger(form, "htmx:abort");
    box.focus();
  });

  // ② A question is on its way: Send hides itself while the answer streams, so the focus goes to the box.
  form.addEventListener("htmx:before:request", () => {
    isStopping = false;
    hasStarted = false;
    if (document.activeElement === send) {
      box.focus();
    }
  });

  // ③ The answer's first event is in the page, your question with it: the box is cleared for the next one.
  form.addEventListener("htmx:sse:after:message", () => {
    if (!hasStarted) {
      hasStarted = true;
      box.value = "";
      box.focus();
    }
  });

  // ④ Each event put into the page keeps the newest message in view.
  form.addEventListener("htmx:after:swap", showNewest);

  /** The text cut to at most so many characters, whole ones: an emoji is never cut in half (issue 57). */
  function cut(text, characters) {
    return Array.from(text).slice(0, characters).join("");
  }

  /**
   * The conversation so far, for the next question: each question with its answer, as text, an answer that failed left
   * out with its question; the newest turns only, within the server's limits, which the page holds.
   */
  function rememberConversation() {
    const limits = messages.dataset;
    const turns = [];
    let question = null;
    for (const item of messages.children) {
      if (item.classList.contains("message-user")) {
        question = item.querySelector(".bubble").textContent.trim();
        continue;
      }
      const answer = item.id.startsWith("turn-") && !item.classList.contains("message-error")
        ? (item.querySelector(".answer").innerText || "").trim()
        : "";
      if (question && answer) {
        turns.push([cut(question, +limits.questionMaxChars), cut(answer, +limits.answerMaxChars)]);
      }
      question = null;
    }
    const kept = turns.slice(-(+limits.historyMaxMessages / 2));
    while (kept.length && kept.flat().join("").length > +limits.historyMaxChars) {
      kept.shift();
    }
    const sent = kept.flatMap(([q, a]) => [{ role: "user", text: q }, { role: "assistant", text: a }]);
    historyField.value = JSON.stringify(sent);
  }

  // ⑤ The stream has ended. An answer still busy never got its end: it was stopped, or cut off on the way. A stream
  // that ended before its first event was cut off too; your question is still in the box. Either way, the
  // conversation so far is what goes back with the next question.
  form.addEventListener("htmx:sse:close", () => {
    const busy = messages.querySelector('.message[aria-busy="true"]');
    if (busy) {
      endWithNote(busy, isStopping ? messages.dataset.stopped : messages.dataset.cutOff);
    } else if (!hasStarted && !isStopping) {
      showError(messages.dataset.cutOff);
    }
    rememberConversation();
  });

  // ⑥ A response that isn't ours, such as another service's error page, is never shown: our own sentence instead.
  form.addEventListener("htmx:before:swap", (event) => {
    const response = event.detail.ctx.response;
    const isStream = (response.headers.get("content-type") || "").startsWith("text/event-stream");
    const isOurs = isStream ? response.status === 200 : response.headers.has("x-nimbus-error");
    if (!isOurs) {
      event.preventDefault();
      showError(messages.dataset.unreachable);
    }
  });

  // ⑦ No answer at all: the chat couldn't be reached, unless Stop came before the answer began.
  form.addEventListener("htmx:error", () => {
    if (!isStopping) {
      showError(messages.dataset.unreachable);
    }
  });

  // ⑨ New chat: the conversation starts over, on the page and in what goes back; an answer under way stops first.
  document.getElementById("new-chat").addEventListener("click", () => {
    if (messages.querySelector('.message[aria-busy="true"]')) {
      isStopping = true;
      htmx.trigger(form, "htmx:abort");
    }
    while (messages.children.length > 1) {
      messages.lastElementChild.remove();
    }
    historyField.value = "[]";
    box.focus();
  });

  // ⑧ Your browser's language and time zone go with each question: the answer's units, and your own today.
  document.getElementById("locale").value = navigator.language || "";
  document.getElementById("time-zone").value = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
})();
