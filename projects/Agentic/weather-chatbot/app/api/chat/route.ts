/*
 * app/api/chat/route.ts: the chat endpoint, POST /api/chat, which the chat page's useChat calls. It checks the body,
 * opens the chosen lane and streams the answer from runChat().
 */
import { parseChatRequest } from "@/lib/chat/chat-request";
import { getChatModel } from "@/lib/chat/model";
import { runChat } from "@/lib/chat/run-chat";
import { InputError, toErrorResponse } from "@/lib/errors";
import { openLane } from "@/lib/lanes/open-lane";
import { logError } from "@/lib/logger";

// The function stops at 60 s; the answer's own budget is 50 s (PLAN.md 9.3).
export const maxDuration = 60;

/** Streams the answer to one chat turn; before the answer starts, a failure gets a plain sentence (400, 503 or 500). */
export async function POST(request: Request): Promise<Response> {
  try {
    // ① Check the body: the messages, their sizes, the lane.
    const body: unknown = await request.json().catch(() => {
      throw new InputError("its body isn't JSON.");
    });
    const chatRequest = await parseChatRequest(body);
    // ② The model (ConfigError if GOOGLE_API_KEY isn't set), and the lane the user picked.
    const model = getChatModel();
    const lane = openLane(chatRequest.laneId);
    // ③ Hand over: runChat() streams the answer, and Stop (the request's signal) cancels it.
    return await runChat(chatRequest, { model, lane, signal: request.signal });
  } catch (error) {
    // ④ Anything that fails before the answer starts gets a plain sentence (PLAN.md 9.2), never the error's own text;
    // all but a refused request also go to the logs.
    if (!(error instanceof InputError)) {
      logError("chat.failed", error);
    }
    return toErrorResponse(error);
  }
}
