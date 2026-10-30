/*
 * lib/lanes/lane.ts: what an open lane gives the chat: the tools the model sees, any tool's own time budget, and how to
 * close the lane once the answer ends, however it ends; what the model reads of a tool's result, on every lane; and the
 * sentence a chip shows when an auth lane falls back.
 */
import "server-only";
import type { JSONValue, ToolSet } from "ai";
import { LANE_BY_ID } from "@/lib/constants";
import {
  type AppError,
  AuthError,
  BudgetExceededError,
  ContractError,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import type { LaneId, LiveLaneId, ToolResult } from "@/lib/types";
import { toRef } from "@/lib/utils";

/**
 * An open lane. `toolBudgetsMs` gives a tool its own time budget, when the usual 8 s is too short (an Actor run on
 * Apify); `close` runs once the answer ends, and a REST lane has nothing to close.
 */
export type Lane = {
  id: LiveLaneId;
  tools: ToolSet;
  toolBudgetsMs?: Readonly<Record<string, number>>;
  close: () => Promise<void>;
};

/**
 * What the model reads of any tool's result, on every lane: the weather only. The request, its time and a fallback's
 * sentence are for the page.
 */
export function toModelWeather<Output extends JSONValue>({
  output,
}: {
  output: ToolResult<Output>;
}): {
  type: "json";
  value: Output;
} {
  return { type: "json", value: output.result };
}

/** Why an auth lane couldn't answer, in words for the chip. */
function toFallbackReason(failure: AppError): string {
  if (failure instanceof AuthError) {
    return "Apify didn't accept our token";
  }
  if (failure instanceof BudgetExceededError) {
    return "Apify's credit for this month is used up";
  }
  if (failure instanceof UpstreamTimeoutError) {
    return "Apify took too long";
  }
  if (failure instanceof UpstreamRateLimitedError) {
    return "Apify is busy";
  }
  if (failure instanceof UpstreamUnavailableError) {
    return "Apify can't be reached";
  }
  if (failure instanceof ContractError) {
    return "Apify answered in a way we didn't expect";
  }
  return "something went wrong";
}

/**
 * The sentence a chip shows when an auth lane falls back (PLAN.md 5.5): which lane couldn't answer and why, and which
 * answered instead; with the ref when the failure is logged as an error.
 */
export function toFallbackSentence(failure: AppError, from: LaneId, to: LaneId, requestId: string): string {
  const [fromLabel, toLabel] = [LANE_BY_ID[from].label, LANE_BY_ID[to].label];
  const sentence = `${fromLabel} is unavailable: ${toFallbackReason(failure)}. Answered through ${toLabel} instead.`;
  return failure.level === "error" ? `${sentence} (ref ${toRef(requestId)})` : sentence;
}
