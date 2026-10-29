/*
 * app/page.tsx: the chat page. It hands the chat window the compare view's four requests, worked out on the server;
 * the conversation itself runs in the browser, through /api/chat.
 */
import type { ReactNode } from "react";
import { ChatWindow } from "@/components/chat-window";
import { COMPARE_CELLS } from "@/lib/chat/lane-examples";

/** The chat page: the chat window, centred on the mint background. */
export default function ChatPage(): ReactNode {
  return (
    <main className="chat-page">
      <ChatWindow compareCells={COMPARE_CELLS} />
    </main>
  );
}
