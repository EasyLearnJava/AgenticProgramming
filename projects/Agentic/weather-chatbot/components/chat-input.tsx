/*
 * components/chat-input.tsx: the rounded input at the bottom of the chat, with the location pin. In step 2 it's shown
 * but switched off: the live chat arrives in step 3.
 */
import type { ReactNode } from "react";

/** The question box; the microphone stays hidden until voice input is built (PLAN.md, step 13). */
export function ChatInput(): ReactNode {
  return (
    <div className="chat-input-area">
      <form className="chat-input" aria-label="Ask about the weather">
        <button type="button" className="icon-button" disabled aria-label="Use my location">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path
              fill="currentColor"
              d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z"
            />
          </svg>
        </button>
        <label className="visually-hidden" htmlFor="question">
          Your question
        </label>
        <input id="question" type="text" placeholder="Type something…" disabled />
        <button type="submit" className="send-button" disabled>
          Send
        </button>
      </form>
      <p className="chat-input-note">The live chat arrives in step 3. Until then, this is a sample conversation.</p>
    </div>
  );
}
