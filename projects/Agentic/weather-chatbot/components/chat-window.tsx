/*
 * components/chat-window.tsx: the chat card: the lane picker, the conversation with its tool calls, the input, and
 * the compare view. useChat sends each question to /api/chat, with the chosen lane, and streams the answer in.
 */
"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { type ReactNode, useState } from "react";
import { ChatInput } from "@/components/chat-input";
import { ChatMessage } from "@/components/chat-message";
import { ChatWelcome } from "@/components/chat-welcome";
import { CompareGrid } from "@/components/compare-grid";
import { LanePicker } from "@/components/lane-picker";
import { useLaneStatus } from "@/hooks/use-lane-status";
import { useNearbyCity } from "@/hooks/use-nearby-city";
import { CHAT_API_PATH, DEFAULT_LANE_ID, MAX_HISTORY_CHARS, MAX_MESSAGES, OWN_ERROR_HEADER } from "@/lib/constants";
import type { ChatMessage as ChatMessageData, CompareCell, LiveLaneId } from "@/lib/types";
import { isAwaitingWords } from "@/lib/utils";

type ChatWindowProps = { compareCells: readonly CompareCell[]; availableLaneIds: readonly LiveLaneId[] };

const UNREACHABLE_MESSAGE = "The chat couldn't be reached. Please try again.";
const HTTP_UNAVAILABLE = 503;

/** The messages to send: the most recent ones, starting with one of yours, within the chat's limits. */
function toRecentMessages(messages: ChatMessageData[]): ChatMessageData[] {
  let recent = messages.slice(-MAX_MESSAGES);
  while (recent.length > 1 && (recent[0]?.role !== "user" || JSON.stringify(recent).length > MAX_HISTORY_CHARS)) {
    recent = recent.slice(1);
  }
  return recent;
}

/**
 * Asks /api/chat. An error that isn't the chat's own (a network failure, or one of Vercel's pages) becomes one plain
 * sentence, so the page never shows another service's text; a Stop is passed on as it is.
 */
async function fetchChat(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch (error) {
    if (init?.signal?.aborted) {
      throw error;
    }
    return new Response(UNREACHABLE_MESSAGE, { status: HTTP_UNAVAILABLE });
  }
  if (response.ok || response.headers.has(OWN_ERROR_HEADER)) {
    return response;
  }
  return new Response(UNREACHABLE_MESSAGE, { status: response.status });
}

const CHAT_TRANSPORT = new DefaultChatTransport<ChatMessageData>({
  api: CHAT_API_PATH,
  fetch: fetchChat,
  // A long chat sends only its recent messages, so a question never fails for the chat's length.
  prepareSendMessagesRequest: ({ id, messages, body, trigger, messageId }) => ({
    body: { ...body, id, messages: toRecentMessages(messages), trigger, messageId },
  }),
});

/** What a screen reader hears when an answer ends: the answer, or that it stopped or failed. */
function toAnnouncement({
  message,
  isAbort,
  isError,
}: {
  message: ChatMessageData;
  isAbort: boolean;
  isError: boolean;
}): string {
  if (isError) {
    return "The answer failed.";
  }
  if (isAbort) {
    return "Stopped.";
  }
  return `Nimbus answered: ${message.parts.map((part) => (part.type === "text" ? part.text : "")).join("")}`;
}

/** The live chat, through the chosen lane; the compare view shows one call through all four lanes. */
export function ChatWindow({ compareCells, availableLaneIds }: ChatWindowProps): ReactNode {
  // ① The lane the next question goes through, whether the compare view is open, and what to announce.
  const [laneId, setLaneId] = useState<LiveLaneId>(DEFAULT_LANE_ID);
  const [isComparing, setIsComparing] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  // ② The conversation: useChat keeps the messages and streams each answer in.
  const { messages, setMessages, sendMessage, regenerate, stop, status, error, clearError } = useChat<ChatMessageData>({
    transport: CHAT_TRANSPORT,
    onFinish: (finished) => setAnnouncement(toAnnouncement(finished)),
  });
  const isBusy = status === "submitted" || status === "streaming";
  const nearbyCity = useNearbyCity();
  const laneHealths = useLaneStatus();
  // The browser's locale picks the units to start with; its time zone says which days "today" and "tomorrow" are.
  const requestBody = (): { laneId: LiveLaneId; locale: string; timeZone: string } => ({
    laneId,
    locale: navigator.language,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  });

  // ③ Asking, retrying, stopping, and starting over.
  function ask(question: string): void {
    void sendMessage({ text: question, metadata: { createdAt: Date.now() } }, { body: requestBody() });
  }
  function retry(): void {
    void regenerate({ body: requestBody() });
  }
  function stopAnswer(): void {
    void stop();
  }
  function startNewChat(): void {
    setMessages([]);
    clearError();
    setAnnouncement("");
  }

  // ④ The card: title and switches, lane picker, conversation, input. Then the compare view, when it's open.
  return (
    <>
      <section className="chat-card" aria-labelledby="chat-title">
        <header className="chat-header">
          <div>
            <h1 id="chat-title" className="chat-title">
              Nimbus (Weather)
            </h1>
            <p className="chat-subtitle">
              Ask about the weather anywhere. Each answer shows the tool calls behind it, and the lane each one took.
            </p>
          </div>
          <div className="chat-header-actions">
            {messages.length > 0 && !isBusy ? (
              <button type="button" className="new-chat-button" onClick={startNewChat}>
                New chat
              </button>
            ) : null}
            <button
              type="button"
              className="compare-toggle"
              aria-pressed={isComparing}
              onClick={() => setIsComparing((wasComparing) => !wasComparing)}
            >
              Compare the four lanes
            </button>
          </div>
        </header>
        <LanePicker value={laneId} onChange={setLaneId} availableLaneIds={availableLaneIds} healths={laneHealths} />
        <ol className="messages" aria-label="Conversation">
          {messages.length === 0 ? <ChatWelcome onPick={ask} isBusy={isBusy} nearbyCity={nearbyCity} /> : null}
          {messages.map((message, index) => (
            <ChatMessage key={message.id} message={message} isAnswering={isBusy && index === messages.length - 1} />
          ))}
          {isAwaitingWords(status, messages.at(-1)) ? (
            <li className="message message-bot">
              <p className="typing" role="status">
                <span className="spinner" aria-hidden="true" />
                Nimbus is checking the weather…
              </p>
            </li>
          ) : null}
        </ol>
        {error ? (
          <div className="chat-error" role="alert">
            <p>{error.message}</p>
            <button type="button" className="send-button" onClick={retry}>
              Try again
            </button>
          </div>
        ) : null}
        <ChatInput isBusy={isBusy} onSend={ask} onStop={stopAnswer} />
        <p className="visually-hidden" aria-live="polite">
          {announcement}
        </p>
      </section>
      {isComparing ? <CompareGrid cells={compareCells} availableLaneIds={availableLaneIds} /> : null}
    </>
  );
}
