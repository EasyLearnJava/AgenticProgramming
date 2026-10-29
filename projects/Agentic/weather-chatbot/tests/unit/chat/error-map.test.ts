/*
 * tests/unit/chat/error-map.test.ts: the error map (PLAN.md 9.2), played out: each class, triggered the way it happens
 * in a chat turn (Open-Meteo slow, failing or refusing; the model failing or calling a tool wrong; a bug; Stop), and
 * what the page shows for it and the line it logs. InputError and ConfigError come before the answer starts:
 * tests/unit/app/api/chat/route.test.ts plays those.
 */
import { APICallError, RetryError, type ToolSet } from "ai";
import { MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import type { ChatRequest } from "@/lib/chat/chat-request";
import { type AnswerBudgets, runChat } from "@/lib/chat/run-chat";
import type { Lane } from "@/lib/lanes/lane";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { step, textStep, toChunks, toolCall } from "@/tests/stubs/model-stand-ins";
import { createFakeFetch, createMemoryCache, type FakeAnswer, hangingFetch } from "@/tests/stubs/open-meteo-stand-ins";

const REQUEST_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";
const REF = "(ref b1a0d9e8)";
const CHAT_REQUEST: ChatRequest = {
  chatId: "chat-1",
  laneId: "rest-no-auth",
  locale: "en-GB",
  messages: [
    { id: "u1", role: "user", parts: [{ type: "text", text: "Weather in Paris?" }], metadata: { createdAt: 1 } },
  ],
};
// A tool's own budget short enough to run out in a test.
const SHORT_TOOL_BUDGET: AnswerBudgets = { totalMs: 60_000, firstChunkMs: 10_000, toolMs: 50 };

/** A model that geocodes Paris (or calls the tool given, with this input), then writes a short answer. */
function oneCallThenAnswer(toolName = "geocode_location", input: unknown = { query: "Paris" }): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doStream: [step([toolCall("call-1", toolName, input)], "tool-calls"), textStep("Sorry, I couldn't check.")],
  });
}

type Turn = {
  model: MockLanguageModelV4;
  answers?: FakeAnswer[] | typeof fetch;
  lane?: (lane: Lane) => Lane;
  budgets?: AnswerBudgets;
  stopAfterMs?: number;
};

/**
 * Plays one turn on REST · no auth: the sentences the page shows (each failed chip's last one, since a bad call gets one
 * for its input and one for its output; then the error box's), and the lines logged.
 */
async function play({ model, answers = [], lane = (opened) => opened, budgets, stopAfterMs }: Turn) {
  const { log, lines } = createTestLog();
  const fetch = typeof answers === "function" ? answers : createFakeFetch(answers).fetch;
  const openMeteo = createOpenMeteoClient({ fetch, cache: createMemoryCache(), random: () => 0 });
  const controller = new AbortController();
  if (stopAfterMs !== undefined) {
    setTimeout(() => controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" })), stopAfterMs);
  }
  const response = await runChat(CHAT_REQUEST, {
    model,
    lane: lane(openRestNoAuthLane({ openMeteo, log })),
    signal: controller.signal,
    requestId: REQUEST_ID,
    log,
    budgets,
  });
  const chunks = toChunks(await response.text());
  const byCall = new Map<string, string>();
  const box: string[] = [];
  for (const chunk of chunks.filter((each) => typeof each.errorText === "string")) {
    if (typeof chunk.toolCallId === "string") {
      byCall.set(chunk.toolCallId, chunk.errorText);
    } else {
      box.push(chunk.errorText);
    }
  }
  const shown = [...byCall.values(), ...box];
  return { shown, lines };
}

/** The lane with its geocoding tool broken by a bug. */
function withBug(lane: Lane): Lane {
  const broken = async (): Promise<never> => {
    throw new TypeError("Cannot read properties of undefined (reading 'results')");
  };
  const tools: ToolSet = Object.fromEntries(
    Object.entries(lane.tools).map(([name, tool]) => [
      name,
      name === "geocode_location" ? ({ ...tool, execute: broken } as typeof tool) : tool,
    ]),
  );
  return { ...lane, tools };
}

const fail503 = () => new Response("", { status: 503 });

const CASES = [
  {
    errorClass: "UpstreamTimeoutError",
    how: "Open-Meteo doesn't answer within the tool's budget",
    turn: (): Turn => ({ model: oneCallThenAnswer(), answers: hangingFetch, budgets: SHORT_TOOL_BUDGET }),
    shown: "The weather service took too long to answer. Please try again.",
    line: { level: "warn", event: "tool.call", tool: "geocode_location" },
  },
  {
    errorClass: "UpstreamUnavailableError",
    how: "Open-Meteo answers 503, twice",
    turn: (): Turn => ({ model: oneCallThenAnswer(), answers: [fail503, fail503] }),
    shown: "The weather service can't be reached right now. Please try again in a minute.",
    line: { level: "warn", event: "tool.call", tool: "geocode_location" },
  },
  {
    errorClass: "UpstreamRateLimitedError",
    how: "Open-Meteo answers 429, with a Retry-After too long to wait",
    turn: (): Turn => ({
      model: oneCallThenAnswer(),
      answers: [{ fixture: "geocode-paris", status: 429, headers: { "retry-after": "60" } }],
    }),
    shown: "The weather service is busy. Please try again in a minute.",
    line: { level: "warn", event: "tool.call", tool: "geocode_location" },
  },
  {
    errorClass: "ContractError",
    how: "Open-Meteo refuses the request with 400",
    turn: (): Turn => ({ model: oneCallThenAnswer(), answers: [{ fixture: "error-17-days", status: 400 }] }),
    shown: `The weather service answered in a way we didn't expect. Please try again later. ${REF}`,
    line: { level: "error", event: "tool.call", tool: "geocode_location" },
  },
  {
    errorClass: "BadToolCallError",
    how: "the model asks for 30 days of forecast, where the tool takes at most 16",
    turn: (): Turn => ({
      model: oneCallThenAnswer("get_forecast", {
        latitude: 48.8534123,
        longitude: 2.3488123,
        days: 30,
        includeHourly: false,
        units: "metric",
      }),
    }),
    shown: "The assistant called a weather tool the wrong way. Please try again.",
    line: { level: "warn", event: "tool.call", tool: "get_forecast" },
  },
  {
    errorClass: "ModelError",
    how: "Gemini answers 503, and AI SDK's two retries do too",
    turn: (): Turn => ({
      model: new MockLanguageModelV4({
        doStream: async () => {
          const unavailable = new APICallError({
            message: "Service Unavailable",
            url: "https://generativelanguage.googleapis.com/v1beta/models/gemini:streamGenerateContent",
            requestBodyValues: {},
            statusCode: 503,
          });
          throw new RetryError({
            message: "Failed after 3 attempts. Last error: Service Unavailable",
            reason: "maxRetriesExceeded",
            errors: [unavailable, unavailable, unavailable],
          });
        },
      }),
    }),
    shown: `The assistant didn't answer. Please try again. ${REF}`,
    line: { level: "error", event: "chat.failed" },
  },
  {
    errorClass: "UnexpectedError",
    how: "a bug in a tool",
    turn: (): Turn => ({ model: oneCallThenAnswer(), lane: withBug }),
    shown: `Something went wrong. ${REF}`,
    line: { level: "error", event: "tool.call", tool: "geocode_location", causeClass: "TypeError" },
  },
];

describe("the error map, in a chat turn", () => {
  it.each(CASES)("$errorClass, when $how: the page's sentence, and one line at its level", async (each) => {
    const { shown, lines } = await play(each.turn());
    expect(shown).toEqual([each.shown]);
    const failures = lines.filter((line) => line.status === "failed" && line.event !== "upstream.http");
    expect(failures).toEqual([expect.objectContaining({ ...each.line, errorClass: each.errorClass })]);
    // A line never quotes the model's input: exact coordinates, or anything else it sent.
    expect(JSON.stringify(lines)).not.toMatch(/48\.8534123|2\.3488123|"days":30/);
  });

  it("AbortedError, when you press Stop during a tool call: no sentence, and the answer's line says it stopped", async () => {
    const { shown, lines } = await play({ model: oneCallThenAnswer(), answers: hangingFetch, stopAfterMs: 30 });
    expect(shown).toEqual([]);
    expect(lines.filter((line) => line.status === "failed")).toEqual([]);
    expect(lines.at(-1)).toMatchObject({ level: "info", event: "chat.aborted" });
  });
});
