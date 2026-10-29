/*
 * app/api/chat/route.ts: the chat endpoint, POST /api/chat, which the chat page's useChat calls. It checks the body,
 * opens the chosen lane and streams the answer from runChat(); every line it logs carries the request's id.
 */
import { type ChatRequest, parseChatRequest, toQuestion } from "@/lib/chat/chat-request";
import { getChatModel } from "@/lib/chat/model";
import { runChat } from "@/lib/chat/run-chat";
import { CHAT_API_PATH, VERCEL_ID_HEADER } from "@/lib/constants";
import { AbortedError, type AppError, InputError, toAppError, toErrorResponse } from "@/lib/errors";
import { openLane } from "@/lib/lanes/open-lane";
import { type Logger, logFailure, logger, toLaneFields } from "@/lib/logger";
import { toRequestId } from "@/lib/utils";

// The function stops at 60 s; the answer's own budget is 50 s (PLAN.md 9.3).
export const maxDuration = 60;

/**
 * The request's first line: how many messages, and the question's length, never its text (nor a hash of it, which
 * hashing likely questions could match).
 */
function logRequest(log: Logger, chatRequest: ChatRequest): void {
  log.info({
    event: "chat.request",
    messages: chatRequest.messages.length,
    questionChars: toQuestion(chatRequest).length,
    locale: chatRequest.locale,
  });
}

/** The line a request ends with when it fails before the answer starts: refused, stopped, or failed. */
function logEarlyEnd(log: Logger, failure: AppError, ms: number): void {
  if (failure instanceof InputError) {
    logFailure(log, "chat.rejected", failure, { ms });
  } else if (failure instanceof AbortedError) {
    log.info({ event: "chat.aborted", ms, steps: 0 });
  } else {
    logFailure(log, "chat.failed", failure, { ms });
  }
}

/** Streams the answer to one chat turn; before the answer starts, a failure gets a plain sentence (400, 503 or 500). */
export async function POST(request: Request): Promise<Response> {
  // ① The request's id: Vercel's own for it, else a new one. Every line logged for this request carries it, the MCP
  // lane passes it on to /api/mcp, and the page gets it back: an error's sentence ends with its last 8 characters.
  const startedAt = performance.now();
  const requestId = toRequestId(request.headers.get(VERCEL_ID_HEADER));
  let log = logger.child({ requestId, route: CHAT_API_PATH });
  try {
    // ② Check the body: the messages, their sizes, the lane. From here on, each line also names the chat and the lane.
    const body: unknown = await request.json().catch(() => {
      throw new InputError("its body isn't JSON.");
    });
    const chatRequest = await parseChatRequest(body);
    log = log.child({ chatId: chatRequest.chatId, ...toLaneFields(chatRequest.laneId) });
    logRequest(log, chatRequest);
    // ③ The model (ConfigError if GOOGLE_API_KEY isn't set), and the lane the user picked; an MCP lane connects to
    // /api/mcp on this same deployment.
    const model = getChatModel();
    const lane = await openLane(chatRequest.laneId, {
      requestUrl: request.url,
      signal: request.signal,
      requestId,
      log,
    });
    // ④ Hand over: runChat() streams the answer and logs how it went; Stop (the request's signal) cancels it.
    return await runChat(chatRequest, { model, lane, signal: request.signal, requestId, log });
  } catch (error) {
    // ⑤ Anything that fails before the answer starts gets its class's sentence (PLAN.md 9.2), never the error's own
    // text, and the request's last line: refused (bad input), stopped, or failed at its class's level.
    const failure = toAppError(error, request.signal);
    logEarlyEnd(log, failure, Math.round(performance.now() - startedAt));
    return toErrorResponse(failure, requestId);
  }
}
