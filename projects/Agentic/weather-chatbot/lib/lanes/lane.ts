/*
 * lib/lanes/lane.ts: what an open lane gives the chat: the tools the model sees, any tool's own time budget, and how to
 * close the lane once the answer ends, however it ends; what the model reads of a tool's result, on every lane; and the
 * auth lanes' Actor tool, the same at both doors, with its fallback to the twin lane and the sentence its chip shows.
 */
import "server-only";
import type { JSONValue, Tool, ToolSet } from "ai";
import { ACTOR_TOOL_NAME, FALLBACK_MIN_LEFT_MS, LANE_BY_ID, TOOL_TIMEOUT_MS } from "@/lib/constants";
import {
  type AppError,
  AuthError,
  BudgetExceededError,
  ContractError,
  toAppError,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import { type Logger, logFailure } from "@/lib/logger";
import type { ActorForecastInput, Forecast, ForecastInput, LaneId, LiveLaneId, ToolResult } from "@/lib/types";
import type { ApifyClient } from "@/lib/upstream/apify";
import { timeoutSignal, toRef } from "@/lib/utils";
import { openMeteoActor, toForecastInput } from "@/lib/weather/tools/open-meteo-actor";

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

/**
 * What an auth lane's Actor tool uses: its lane and its twin (the no-auth lane behind the same door), the Apify client
 * for its door, how to ask the twin for the same forecast, the request's id and logger, the lane's clock, the run's
 * budget, and when the answer's own budget runs out, on the lane's clock.
 */
export type ActorToolDeps = {
  laneId: LiveLaneId;
  twinLaneId: LiveLaneId;
  apify: ApifyClient;
  runTwin: (input: ForecastInput, signal: AbortSignal) => Promise<ToolResult<Forecast>>;
  requestId: string;
  log: Logger;
  now: () => number;
  actorBudgetMs: number;
  answerDeadline: number;
};

/**
 * An auth lane's copy of Apify's Actor tool, the same at both doors; only the Apify client differs. It runs the Actor,
 * times it, and records the request. If Apify can't answer (a rejected token, used-up credit, too slow, unreachable, a
 * shape we don't read), the same forecast comes from the twin, marked as a fallback, and the failure is logged once,
 * here, where it's handled. When the tool's own signal has fired (Stop, the answer's budget, the tool's), the answer is
 * ending: the failure is passed on, and nothing falls back. Nor does it with under 12 s of the answer left (PLAN.md
 * 9.3): the call fails with its own sentence instead.
 */
export function toActorTool(deps: ActorToolDeps): Tool<ActorForecastInput, ToolResult<Forecast>> {
  const { laneId, twinLaneId, apify, runTwin, requestId, log, now, actorBudgetMs, answerDeadline } = deps;
  return {
    description: openMeteoActor.description,
    inputSchema: openMeteoActor.inputSchema,
    execute: async (input, { abortSignal }) => {
      const startedAt = now();
      try {
        // ④ The call: the Actor's run, through the lane's door, with the tool's first actorBudgetMs (20 s; 25 on MCP,
        // which may connect first): its own timer, joined to the tool's signal.
        const run = await openMeteoActor.run(input, { apify, signal: timeoutSignal(actorBudgetMs, abortSignal), log });
        // ⑤ The result: the Actor's items, as our Forecast (lib/weather/actor-items.ts).
        return {
          result: run.output,
          summary: openMeteoActor.summarize(run.output),
          call: { laneId, wire: run.request, cache: run.cache, durationMs: Math.round(now() - startedAt) },
        };
      } catch (error) {
        if (abortSignal?.aborted) {
          throw error;
        }
        const failure = toAppError(error);
        if (answerDeadline - now() < FALLBACK_MIN_LEFT_MS) {
          throw failure;
        }
        logFailure(log, "lane.fallback", failure, { from: laneId, to: twinLaneId, tool: ACTOR_TOOL_NAME });
        // The twin gets the tool's last 8 s, joined to the same signal, so Stop and the answer's budget still end it.
        const twin = await runTwin(toForecastInput(input), timeoutSignal(TOOL_TIMEOUT_MS, abortSignal));
        return {
          ...twin,
          fallback: { from: laneId, sentence: toFallbackSentence(failure, laneId, twinLaneId, requestId) },
        };
      }
    },
    // The model reads only the weather; the request, the time and the fallback are for the page.
    toModelOutput: toModelWeather,
  };
}
