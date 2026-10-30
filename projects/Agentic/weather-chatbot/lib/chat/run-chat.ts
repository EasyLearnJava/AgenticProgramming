/*
 * lib/chat/run-chat.ts: one chat turn. Streams the model's answer with the chosen lane's tools, within the step cap
 * and the time budgets; logs each tool call, each model step and how the answer ended; and closes the lane however the
 * answer ends.
 */
import "server-only";
import {
  convertToModelMessages,
  createUIMessageStreamResponse,
  isStepCount,
  type LanguageModel,
  type StepResult,
  streamText,
  type ToolExecutionEndEvent,
  type ToolSet,
  toUIMessageStream,
} from "ai";
import { type ChatRequest, HISTORY_TOOLS } from "@/lib/chat/chat-request";
import { toSystemPrompt } from "@/lib/chat/system-prompt";
import {
  ANSWER_TIMEOUT_MS,
  FIRST_CHUNK_TIMEOUT_MS,
  MAX_OUTPUT_TOKENS,
  MAX_STEPS,
  REQUEST_ID_HEADER,
  TOOL_TIMEOUT_MS,
} from "@/lib/constants";
import { AbortedError, toAppError, toUserMessage } from "@/lib/errors";
import type { Lane } from "@/lib/lanes/lane";
import { type Logger, logFailure } from "@/lib/logger";
import type { MessageMetadata, ToolResult } from "@/lib/types";
import { toAbortKind } from "@/lib/utils";

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
  requestId: string;
  log: Logger;
  now?: () => Date;
  budgets?: AnswerBudgets;
};

/**
 * A tool call's line, for every lane: the tool, its time, and whether the cache answered; a failure at its class's
 * level. A stop isn't a failure: the answer's own line says it stopped.
 */
function logToolCall(
  log: Logger,
  { toolCall, toolExecutionMs, toolOutput }: ToolExecutionEndEvent<ToolSet>,
  signal: AbortSignal,
): void {
  const fields = { event: "tool.call", tool: toolCall.toolName, ms: Math.round(toolExecutionMs) };
  if (toolOutput.type === "tool-result") {
    const { call, fallback } = toolOutput.output as ToolResult<unknown>;
    log.info({ ...fields, status: "ok", cache: call.cache, ...(fallback ? { fallbackFrom: fallback.from } : {}) });
    return;
  }
  const failure = toAppError(toolOutput.error, signal);
  if (!(failure instanceof AbortedError)) {
    logFailure(log, fields.event, failure, { tool: fields.tool, ms: fields.ms });
  }
}

/**
 * A model step's line: its number, the model, why it ended, its tokens and tool calls. A tool call the model got wrong
 * (AI SDK marks it invalid, with its error) never runs, so its line is written here; it names the tool only if it's one
 * of the lane's, since a name the model made up comes from its own output.
 */
function logStep(log: Logger, step: StepResult<ToolSet>, tools: ToolSet): void {
  for (const part of step.content) {
    if (part.type === "tool-call" && part.invalid === true) {
      const tool = Object.hasOwn(tools, part.toolName) ? part.toolName : "unknown";
      logFailure(log, "tool.call", toAppError(part.error), { tool });
    }
  }
  log.info({
    event: "model.step",
    step: step.stepNumber,
    model: step.model.modelId,
    finishReason: step.finishReason,
    inputTokens: step.usage.inputTokens,
    outputTokens: step.usage.outputTokens,
    toolCalls: step.toolCalls.length,
  });
}

/** A lane's own tool budgets, as AI SDK names them: the tool's name, then "Ms". */
function toToolBudgets(lane: Lane): Record<string, number> {
  return Object.fromEntries(Object.entries(lane.toolBudgetsMs ?? {}).map(([name, ms]) => [`${name}Ms`, ms]));
}

/** Streams one answer, as a UI message stream: the model's text, and each tool call as it starts and ends. */
export async function runChat(
  chatRequest: ChatRequest,
  { model, lane, signal, requestId, log, now = () => new Date(), budgets = BUDGETS }: RunChatOptions,
): Promise<Response> {
  const startedAt = now();
  const elapsedMs = (): number => now().getTime() - startedAt.getTime();
  // AI SDK still calls onEnd after onError once a step has finished, so an answer that failed must not also say done.
  let hasFailed = false;
  // ① The earlier messages, for the model: each tool result as toModelWeather() gives it (the weather only), found by
  // its tool's name among every lane's tools, since the chat may have changed lanes; and without a tool call that a
  // Stop left unfinished. If they can't be read, the lane is closed before giving up.
  const messages = await convertToModelMessages(chatRequest.messages, {
    tools: HISTORY_TOOLS,
    ignoreIncompleteToolCalls: true,
  }).catch(async (error: unknown) => {
    await lane.close();
    throw error;
  });
  // ② Stream the answer: the rules, the lane's tools, at most 5 steps, and a budget for each part (a lane can give a
  // tool its own). The last step can't call a tool, so an answer never ends on tool results without words.
  const result = streamText({
    model,
    instructions: toSystemPrompt({
      now: startedAt,
      locale: chatRequest.locale,
      timeZone: chatRequest.timeZone,
      toolNames: Object.keys(lane.tools),
    }),
    messages,
    tools: lane.tools,
    stopWhen: isStepCount(MAX_STEPS),
    prepareStep: ({ stepNumber }) => (stepNumber === LAST_STEP_NUMBER ? { toolChoice: "none" } : undefined),
    maxOutputTokens: MAX_OUTPUT_TOKENS,
    timeout: { ...budgets, tools: toToolBudgets(lane) },
    abortSignal: signal,
    // ③ The logs: each tool call and model step, then one line for how the answer ended: done, stopped, cut short by a
    // time budget, or failed. However it ends, the lane is closed.
    onToolExecutionEnd: (event) => logToolCall(log, event, signal),
    onStepEnd: (step) => logStep(log, step, lane.tools),
    onEnd: async ({ steps, totalUsage, finishReason }) => {
      if (!hasFailed) {
        log.info({
          event: "chat.done",
          ms: elapsedMs(),
          steps: steps.length,
          toolCalls: steps.reduce((count, step) => count + step.toolCalls.length, 0),
          inputTokens: totalUsage.inputTokens,
          outputTokens: totalUsage.outputTokens,
          finishReason,
        });
      }
      await lane.close();
    },
    onAbort: async ({ steps }) => {
      const fields = { ms: elapsedMs(), steps: steps.length };
      if (toAbortKind(signal) === "stop") {
        log.info({ event: "chat.aborted", ...fields });
      } else {
        log.warn({ event: "budget.exceeded", ...fields });
      }
      await lane.close();
    },
    onError: async ({ error }) => {
      hasFailed = true;
      logFailure(log, "chat.failed", toAppError(error, signal), { ms: elapsedMs() });
      await lane.close();
    },
  });
  // ④ To the page: when the answer started, and whether a time budget cut it short (the page isn't told otherwise);
  // errors as our plain sentences, with the ref when they're logged as errors; and the request's id, in a header.
  return createUIMessageStreamResponse({
    headers: { [REQUEST_ID_HEADER]: requestId },
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
      onError: (error) => toUserMessage(toAppError(error, signal), requestId),
    }),
  });
}
