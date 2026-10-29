/*
 * components/chat-welcome.tsx: the bot's first message, before you've asked anything, with questions to try.
 */
import type { ReactNode } from "react";

type ChatWelcomeProps = { onPick: (question: string) => void; isBusy: boolean; nearbyCity: string | undefined };

const SUGGESTED_QUESTIONS = [
  "Do I need an umbrella in Paris tomorrow afternoon?",
  "What's the weather in Tokyo right now?",
  "Is the air OK in Delhi today?",
] as const;

/** A hello from Nimbus, and questions to try (one about the nearby city, if Vercel knows it); picking one sends it. */
export function ChatWelcome({ onPick, isBusy, nearbyCity }: ChatWelcomeProps): ReactNode {
  const questions = nearbyCity
    ? [...SUGGESTED_QUESTIONS, `What's the weather in ${nearbyCity} this weekend?`]
    : SUGGESTED_QUESTIONS;
  return (
    <li className="message message-bot">
      <p className="message-meta">
        <span className="avatar" aria-hidden="true">
          N
        </span>
        <span>Nimbus (Weather)</span>
      </p>
      <div className="bubble bubble-bot">
        <p>
          Hi, I’m Nimbus. Ask me about the weather anywhere: now, the next 16 days, or the air. Every number comes from
          Open-Meteo, and each tool call shows above my answer: open one to see the request it sent.
        </p>
      </div>
      <ul className="suggestions" aria-label="Questions to try">
        {questions.map((question) => (
          <li key={question}>
            <button type="button" className="suggestion" disabled={isBusy} onClick={() => onPick(question)}>
              {question}
            </button>
          </li>
        ))}
      </ul>
      {nearbyCity ? (
        <p className="message-hint">
          {nearbyCity} is a guess from your network’s location: a suggestion, never used unless you pick it.
        </p>
      ) : null}
    </li>
  );
}
