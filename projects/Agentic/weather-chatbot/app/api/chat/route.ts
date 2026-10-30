/*
 * app/api/chat/route.ts: the chat endpoint, POST /api/chat, which the chat page's useChat calls. It checks the caller
 * and the body, opens the chosen lane and streams the answer from runChat(); every line it logs carries the request's
 * id.
 */
import { waitUntil } from "@vercel/functions";
import { checkBotId } from "botid/server";
import { isBotIdOn } from "@/lib/botid";
import { type ChatRequest, parseChatRequest, toQuestion } from "@/lib/chat/chat-request";
import { getChatModel } from "@/lib/chat/model";
import { runChat } from "@/lib/chat/run-chat";
import { config } from "@/lib/config";
import { BOTID_TIMEOUT_MS, CHAT_API_PATH, VERCEL_ID_HEADER } from "@/lib/constants";
import {
  AbortedError,
  type AppError,
  BotBlockedError,
  InputError,
  toAppError,
  toErrorResponse,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import { openLane, toAvailableLaneIds } from "@/lib/lanes/open-lane";
import { flushLogs, type Logger, logFailure, logger, toLaneFields } from "@/lib/logger";
import { markTrace } from "@/lib/sentry";
import { timeoutSignal, toRequestId, untilAborted } from "@/lib/utils";

// The function stops at 60 s; the answer's own budget is 50 s (PLAN.md 9.3).
export const maxDuration = 60;

/**
 * The request's first line: how many messages, the question's length, never its text (nor a hash of it, which
 * hashing likely questions could match), and the browser's locale and time zone.
 */
function logRequest(log: Logger, chatRequest: ChatRequest): void {
  log.info({
    event: "chat.request",
    messages: chatRequest.messages.length,
    questionChars: toQuestion(chatRequest).length,
    locale: chatRequest.locale,
    timeZone: chatRequest.timeZone,
  });
}

/**
 * BotID's verdict on the caller, within its own 3 s and the request's signal. If BotID can't answer, the request goes
 * on, with a line that says so: the rate limit still holds, and BotID's trouble mustn't stop the chat.
 */
async function isBot(request: Request, log: Logger): Promise<boolean> {
  try {
    const verdict = await untilAborted(checkBotId(), timeoutSignal(BOTID_TIMEOUT_MS, request.signal));
    // BotID reads Vercel's answer without checking its status, so an error answer comes back with no verdict.
    if (typeof verdict.isBot !== "boolean") {
      throw new Error("BotID gave no verdict.");
    }
    return verdict.isBot;
  } catch (error) {
    if (request.signal.aborted) {
      throw error;
    }
    const failure =
      error instanceof Error && error.name === "TimeoutError"
        ? new UpstreamTimeoutError("BotID didn't answer in time.")
        : new UpstreamUnavailableError("BotID couldn't check the request.", { cause: error });
    logFailure(log, "botid.failed", failure);
    return false;
  }
}

/**
 * The line a request ends with when it fails before the answer starts: refused (a bad message, or BotID's verdict),
 * stopped, or failed.
 */
function logEarlyEnd(log: Logger, failure: AppError, ms: number): void {
  if (failure instanceof InputError || failure instanceof BotBlockedError) {
    logFailure(log, "chat.rejected", failure, { ms });
  } else if (failure instanceof AbortedError) {
    log.info({ event: "chat.aborted", ms, steps: 0 });
  } else {
    logFailure(log, "chat.failed", failure, { ms });
  }
}

/**
 * Streams the answer to one chat turn; before the answer starts, a failure gets a plain sentence (400, 403, 503 or
 * 500).
 */
export async function POST(request: Request): Promise<Response> {
  // ① The request's id: Vercel's own for it, else a new one. Every line logged for this request carries it, the MCP
  // lane passes it on to /api/mcp, and the page gets it back: an error's sentence ends with its last 8 characters.
  const startedAt = performance.now();
  const requestId = toRequestId(request.headers.get(VERCEL_ID_HEADER));
  let log = logger.child({ requestId, route: CHAT_API_PATH });
  markTrace(requestId);
  // On Vercel, the page's going ends this function as soon as it's told (vercel.json turns cancellation on for this
  // route), so it's kept alive until the request's last line is written and its lane closed; then until its lines have
  // gone to Axiom, and its errors to Sentry (step 9).
  const ended = Promise.withResolvers<void>();
  waitUntil(ended.promise.then(flushLogs));
  try {
    // ② The caller: on Vercel, BotID's check, before any work, that a real browser sent the request (step 8).
    if (isBotIdOn() && (await isBot(request, log))) {
      throw new BotBlockedError("BotID found no browser behind the request.");
    }
    // ③ Check the body: the messages, their sizes, the lane. From here on, each line also names the chat and the lane.
    const body: unknown = await request.json().catch((error: unknown) => {
      // A page that goes while its message is read has stopped; it didn't send a bad one.
      throw request.signal.aborted ? error : new InputError("its body isn't JSON.");
    });
    const chatRequest = await parseChatRequest(body, toAvailableLaneIds(config.apify.token));
    log = log.child({ chatId: chatRequest.chatId, ...toLaneFields(chatRequest.laneId) });
    logRequest(log, chatRequest);
    // ④ The model (ConfigError if GOOGLE_API_KEY isn't set), and the lane the user picked; an MCP lane connects to
    // /api/mcp on this same deployment.
    const model = getChatModel();
    const lane = await openLane(chatRequest.laneId, {
      requestUrl: request.url,
      signal: request.signal,
      requestId,
      log,
    });
    // ⑤ Hand over: runChat() streams the answer and logs how it went; Stop, or the page's going, cancels it through the
    // request's signal (on Vercel too: vercel.json turns cancellation on for this route).
    return await runChat(chatRequest, {
      model,
      lane,
      signal: request.signal,
      requestId,
      log,
      onEnded: ended.resolve,
    });
  } catch (error) {
    // ⑥ Anything that fails before the answer starts gets its class's sentence (PLAN.md 9.2), never the error's own
    // text, and the request's last line: refused (bad input, or a bot), stopped, or failed at its class's level.
    const failure = toAppError(error, request.signal);
    try {
      logEarlyEnd(log, failure, Math.round(performance.now() - startedAt));
    } finally {
      ended.resolve();
    }
    return toErrorResponse(failure, requestId);
  }
}
