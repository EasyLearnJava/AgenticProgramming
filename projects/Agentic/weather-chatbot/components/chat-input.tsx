/*
 * components/chat-input.tsx: the rounded input at the bottom of the chat: the location pin, the question box, and Send
 * (Stop while an answer is coming).
 */
"use client";

import { type FormEvent, type ReactNode, useRef, useState } from "react";
import { LOCATION_MAX_AGE_MS, LOCATION_TIMEOUT_MS, MAX_MESSAGE_CHARS } from "@/lib/constants";
import { roundCoordinate } from "@/lib/utils";

type ChatInputProps = { isBusy: boolean; onSend: (question: string) => void; onStop: () => void };

/** The question box. The pin asks the browser for your location, only when clicked; the microphone stays hidden. */
export function ChatInput({ isBusy, onSend, onStop }: ChatInputProps): ReactNode {
  const [text, setText] = useState("");
  const [locationNote, setLocationNote] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // ① Send: a question that isn't empty, while no answer is coming.
  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const question = text.trim();
    if (question === "" || isBusy) {
      return;
    }
    onSend(question);
    setText("");
  }

  // ② The pin: your position, rounded to about 1 km, goes into the question for you to edit and send.
  function askForLocation(): void {
    if (!("geolocation" in navigator)) {
      setLocationNote("This browser can't share its location.");
      return;
    }
    setLocationNote("Asking the browser for your location…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const point = `${roundCoordinate(coords.latitude)}, ${roundCoordinate(coords.longitude)}`;
        setText(`What's the weather at my location (${point})?`);
        setLocationNote(`Your location, rounded to about 1 km: ${point}. Edit the question if you like, then send it.`);
        inputRef.current?.focus();
      },
      (error) => setLocationNote(`Your location isn't available: ${error.message}`),
      { maximumAge: LOCATION_MAX_AGE_MS, timeout: LOCATION_TIMEOUT_MS },
    );
  }

  return (
    <div className="chat-input-area">
      <form className="chat-input" aria-label="Ask about the weather" onSubmit={submit}>
        <button type="button" className="icon-button" aria-label="Use my location" onClick={askForLocation}>
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
        <input
          id="question"
          ref={inputRef}
          type="text"
          placeholder="Type something…"
          autoComplete="off"
          maxLength={MAX_MESSAGE_CHARS}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        {isBusy ? (
          <button type="button" className="send-button" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button type="submit" className="send-button" disabled={text.trim() === ""}>
            Send
          </button>
        )}
      </form>
      {locationNote === "" ? null : (
        <p className="chat-input-note" aria-live="polite">
          {locationNote}
        </p>
      )}
      <p className="chat-input-note">
        Your questions go to Google’s Gemini to be answered, so don’t share personal details. Weather data by
        Open-Meteo.com.
      </p>
    </div>
  );
}
