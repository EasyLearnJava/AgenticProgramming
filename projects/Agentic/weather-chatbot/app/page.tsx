/*
 * app/page.tsx: the chat page. It hands the chat window the sample conversation, already worked out for each lane on
 * the server; the live chat replaces it in step 3.
 */
import type { ReactNode } from "react";
import { ChatWindow } from "@/components/chat-window";
import { SAMPLE_COMPARE_CELLS, SAMPLE_MESSAGES_BY_LANE } from "@/lib/chat/sample-conversation";

/** The chat page: the chat window, centred on the mint background. */
export default function ChatPage(): ReactNode {
  return (
    <main className="chat-page">
      <ChatWindow messagesByLane={SAMPLE_MESSAGES_BY_LANE} compareCells={SAMPLE_COMPARE_CELLS} />
    </main>
  );
}
