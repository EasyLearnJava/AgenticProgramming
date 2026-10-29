/*
 * lib/chat/run-chat.ts: one chat turn. Streams the model's answer with the chosen lane's tools, within the step cap
 * and the time budgets, and closes the lane however the answer ends.
 */
import "server-only";
import {
  convertToModelMessages,
  createUIMessageStreamResponse,
  isStepCount,
  type LanguageModel,
  streamText,
  toUIMessageStream,
} from "ai";
import type { ChatRequest } from "@/lib/chat/chat-request";
import { toSystemPrompt } from "@/lib/chat/system-prompt";
import {
  ANSWER_TIMEOUT_MS,
  FIRST_CHUNK_TIMEOUT_MS,
  MAX_OUTPUT_TOKENS,
  MAX_STEPS,
  TOOL_TIMEOUT_MS,
} from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import type { Lane } from "@/lib/lanes/lane";
import { logError } from "@/lib/logger";
import type { MessageMetadata } from "@/lib/types";

/** The time budgets of one answer (PLAN.md 9.3): the whole answer, the model's first chunk, and each tool call. */
export type AnswerBudgets = { totalMs: number; firstChunkMs: number; toolMs: number };

const BUDGETS: AnswerBudgets = {
  totalMs: ANSWER_TIMEOUT_MS,
  firstChunkMs: FIRST_CHUNK_TIMEOUT_MS,
  toolMs: TOOL_TIMEOUT_MS,
};
const LAST_STEP_NUMBER = MAX_STEPS - 1;

type RunChatOptions = {
  model: LanguageModel;
  lane: Lane;
  signal: AbortSignal;
  now?: () => Date;
  budgets?: AnswerBudgets;
};

/** Streams one answer, as a UI message stream: the model's text, and each tool call as it starts and ends. */
export async function runChat(
  chatRequest: ChatRequest,
  { model, lane, signal, now = () => new Date(), budgets = BUDGETS }: RunChatOptions,
): Promise<Response> {
  const startedAt = now();
  // ① The earlier messages, for the model: each tool result as the tool's toModelOutput gives it (the weather only),
  // and without a tool call that a Stop left unfinished. If they can't be read, the lane is closed before giving up.
  const messages = await convertToModelMessages(chatRequest.messages, {
    tools: lane.tools,
    ignoreIncompleteToolCalls: true,
  }).catch(async (error: unknown) => {
    await lane.close();
    throw error;
  });
  // ② Stream the answer: the rules, the lane's tools, at most 5 steps, and a budget for each part. The last step
  // can't call a tool, so an answer never ends on tool results without words.
  const result = streamText({
    model,
    instructions: toSystemPrompt({ now: startedAt, locale: chatRequest.locale }),
    messages,
    tools: lane.tools,
    stopWhen: isStepCount(MAX_STEPS),
    prepareStep: ({ stepNumber }) => (stepNumber === LAST_STEP_NUMBER ? { toolChoice: "none" } : undefined),
    maxOutputTokens: MAX_OUTPUT_TOKENS,
    timeout: budgets,
    abortSignal: signal,
    // ③ Close the lane however the answer ends: finished, stopped or timed out, or failed; a failure is logged first.
    onEnd: lane.close,
    onAbort: lane.close,
    onError: async ({ error }) => {
      logError("chat.failed", error, { lane: lane.id });
      await lane.close();
    },
  });
  // ④ To the page: when the answer started, and whether a time budget cut it short (the page isn't told otherwise);
  // errors as our plain sentences, never an upstream's text.
  return createUIMessageStreamResponse({
    stream: toUIMessageStream({
      stream: result.stream,
      tools: lane.tools,
      originalMessages: chatRequest.messages,
      sendReasoning: false,
      messageMetadata: ({ part }): MessageMetadata | undefined => {
        if (part.type === "start") {
          return { createdAt: startedAt.getTime() };
        }
        return part.type === "abort" ? { createdAt: startedAt.getTime(), isCutShort: true } : undefined;
      },
      onError: toUserMessage,
    }),
  });
}
