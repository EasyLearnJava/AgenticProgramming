/*
 * components/chat-message.tsx: one message: who and when, the tool calls it made, its text, and its weather card.
 */
import type { ReactNode } from "react";
import { ToolChip } from "@/components/tool-chip";
import { WeatherCard } from "@/components/weather-card";
import type { MessageView } from "@/lib/types";

type ChatMessageProps = { message: MessageView };

/** One message of the conversation: the bot's on the left, yours on the right. */
export function ChatMessage({ message }: ChatMessageProps): ReactNode {
  const isBot = message.role === "bot";
  return (
    <li className={`message message-${message.role}`}>
      <p className="message-meta">
        {isBot ? (
          <span className="avatar" aria-hidden="true">
            N
          </span>
        ) : null}
        <span>{isBot ? "Nimbus (Weather)" : "You"}</span>
        <span aria-hidden="true">·</span>
        <time>{message.time}</time>
      </p>
      {message.toolCalls?.length ? (
        <div className="tool-chips">
          {message.toolCalls.map((call) => (
            <ToolChip key={call.id} call={call} />
          ))}
        </div>
      ) : null}
      <p className={isBot ? "bubble bubble-bot" : "bubble bubble-user"}>{message.text}</p>
      {message.forecast ? <WeatherCard forecast={message.forecast} /> : null}
    </li>
  );
}
