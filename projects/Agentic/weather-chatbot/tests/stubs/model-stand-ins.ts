/*
 * tests/stubs/model-stand-ins.ts: the pieces of a mock model's answer, as AI SDK's MockLanguageModelV4 streams them
 * in place of Gemini, and the page's view of a UI message stream.
 */
import type { LanguageModelV4StreamPart } from "@ai-sdk/provider";

const USAGE = {
  inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 5, text: 5, reasoning: 0 },
};

/** One model step: it streams these parts, then finishes for the given reason, having used 10 tokens in and 5 out. */
export function step(parts: LanguageModelV4StreamPart[], reason: "tool-calls" | "stop") {
  return {
    stream: new ReadableStream<LanguageModelV4StreamPart>({
      start(controller) {
        for (const part of [{ type: "stream-start", warnings: [] }, ...parts] as LanguageModelV4StreamPart[]) {
          controller.enqueue(part);
        }
        controller.enqueue({ type: "finish", usage: USAGE, finishReason: { unified: reason, raw: undefined } });
        controller.close();
      },
    }),
  };
}

/** A tool call, as a model streams it: the input as JSON text. */
export function toolCall(toolCallId: string, toolName: string, input: unknown): LanguageModelV4StreamPart {
  return { type: "tool-call", toolCallId, toolName, input: JSON.stringify(input) };
}

/** A step that only writes this text, and stops. */
export function textStep(text: string) {
  return step(
    [
      { type: "text-start", id: "text-1" },
      { type: "text-delta", id: "text-1", delta: text },
      { type: "text-end", id: "text-1" },
    ],
    "stop",
  );
}

/** A UI message stream's chunks, from its response body: one `data:` line each, then `[DONE]`. */
export function toChunks(body: string) {
  return body
    .split("\n")
    .filter((line) => line.startsWith("data: ") && line !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)));
}
