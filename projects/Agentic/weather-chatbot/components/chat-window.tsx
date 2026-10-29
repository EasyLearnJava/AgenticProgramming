/*
 * components/chat-window.tsx: the chat card: the lane picker, the conversation with its tool calls, the input, and
 * the compare view. In step 2 the conversation is a sample; the live chat replaces it in step 3.
 */
"use client";

import { type ReactNode, useState } from "react";
import { ChatInput } from "@/components/chat-input";
import { ChatMessage } from "@/components/chat-message";
import { CompareGrid } from "@/components/compare-grid";
import { LanePicker } from "@/components/lane-picker";
import { DEFAULT_LANE_ID } from "@/lib/constants";
import type { CompareCell, LaneId, MessageView } from "@/lib/types";

type ChatWindowProps = {
  messagesByLane: Readonly<Record<LaneId, readonly MessageView[]>>;
  compareCells: readonly CompareCell[];
};

/** The chat, shown through the chosen lane; the compare view shows all four lanes at once. */
export function ChatWindow({ messagesByLane, compareCells }: ChatWindowProps): ReactNode {
  // ① The lane the calls go through, and whether the compare view is open.
  const [laneId, setLaneId] = useState<LaneId>(DEFAULT_LANE_ID);
  const [isComparing, setIsComparing] = useState(false);
  // ② The card: title and compare switch, lane picker, conversation, input. Then the compare view, when it's open.
  return (
    <>
      <section className="chat-card" aria-labelledby="chat-title">
        <header className="chat-header">
          <div>
            <h1 id="chat-title" className="chat-title">
              Nimbus (Weather)
            </h1>
            <p className="sample-note">
              A sample conversation: the plan’s Paris question, answered with Open-Meteo’s real data from 29 October
              2026. Pick a lane to see how each call would travel.
            </p>
          </div>
          <button
            type="button"
            className="compare-toggle"
            aria-pressed={isComparing}
            onClick={() => setIsComparing((wasComparing) => !wasComparing)}
          >
            Compare the four lanes
          </button>
        </header>
        <LanePicker value={laneId} onChange={setLaneId} />
        <ol className="messages" aria-label="Conversation">
          {messagesByLane[laneId].map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
        </ol>
        <ChatInput />
      </section>
      {isComparing ? <CompareGrid cells={compareCells} /> : null}
    </>
  );
}
