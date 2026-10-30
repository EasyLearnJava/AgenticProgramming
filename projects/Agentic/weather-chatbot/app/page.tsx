/*
 * app/page.tsx: the chat page. It hands the chat window the compare view's four requests, and the lanes this
 * deployment can run (an auth lane only with Apify's token), both worked out on the server; the conversation itself
 * runs in the browser, through /api/chat.
 */
import type { ReactNode } from "react";
import { ChatWindow } from "@/components/chat-window";
import { COMPARE_CELLS } from "@/lib/chat/lane-examples";
import { config } from "@/lib/config";
import { toAvailableLaneIds } from "@/lib/lanes/open-lane";

/** The chat page: the chat window, centred on the mint background. */
export default function ChatPage(): ReactNode {
  return (
    <main className="chat-page">
      <ChatWindow compareCells={COMPARE_CELLS} availableLaneIds={toAvailableLaneIds(config.apify.token)} />
    </main>
  );
}
