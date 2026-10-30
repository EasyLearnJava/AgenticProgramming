/*
 * tests/unit/chat/run-chat.test.ts: one whole chat turn, on REST · no auth and through MCP · no auth, with AI SDK's
 * mock model in place of Gemini and Open-Meteo's recorded answers in place of the network: what the page receives,
 * what the model reads (after a change of lane too), and the lines the turn logs.
 */
import type { LanguageModelV4StreamPart } from "@ai-sdk/provider";
import { APICallError } from "ai";
import { MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import { type ChatRequest, parseChatRequest } from "@/lib/chat/chat-request";
import { type AnswerBudgets, runChat } from "@/lib/chat/run-chat";
import { LIVE_LANE_IDS } from "@/lib/constants";
import { openMcpNoAuthLane } from "@/lib/lanes/mcp-no-auth";
import { openRestAuthLane } from "@/lib/lanes/rest-auth";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import { createApifyClient } from "@/lib/upstream/apify";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { createApifyFetch } from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import { step, textStep, toChunks, toolCall } from "@/tests/stubs/model-stand-ins";
import { createFakeFetch, createMemoryCache, type FakeAnswer } from "@/tests/stubs/open-meteo-stand-ins";

const NOW = new Date("2026-10-29T16:00:00Z");
const QUESTION = "Do I need an umbrella in Paris tomorrow afternoon?";
const ANSWER = "No umbrella needed: a 0% chance of rain all afternoon.";

/** The mock model's three steps for the Paris question: geocode, forecast, then the answer. */
function parisModel(): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doStream: [
      step([toolCall("call-1", "geocode_location", { query: "Paris" })], "tool-calls"),
      step(
        [
          toolCall("call-2", "get_forecast", {
            latitude: 48.85341,
            longitude: 2.3488,
            days: 2,
            includeHourly: true,
            units: "metric",
          }),
        ],
        "tool-calls",
      ),
      textStep(ANSWER),
    ],
  });
}

const REQUEST_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";

const CHAT_REQUEST: ChatRequest = {
  chatId: "chat-1",
  laneId: "rest-no-auth",
  locale: "en-GB",
  timeZone: "Europe/London",
  messages: [
    { id: "u1", role: "user", parts: [{ type: "text", text: QUESTION }], metadata: { createdAt: NOW.getTime() } },
  ],
};

/**
 * Runs one turn: the UI message stream's chunks as the page receives them, the lines it logged, and how often the lane
 * was closed.
 */
async function runTurn(model: MockLanguageModelV4, answers: FakeAnswer[], budgets?: AnswerBudgets) {
  const fake = createFakeFetch(answers);
  const openMeteo = createOpenMeteoClient({
    fetch: fake.fetch,
    cache: createMemoryCache(),
    now: () => NOW,
    random: () => 0,
  });
  const { log, lines, events } = createTestLog();
  let closings = 0;
  const lane = {
    ...openRestNoAuthLane({ openMeteo, log }),
    close: async () => {
      closings += 1;
    },
  };
  const signal = new AbortController().signal;
  const response = await runChat(CHAT_REQUEST, {
    model,
    lane,
    signal,
    requestId: REQUEST_ID,
    log,
    now: () => NOW,
    budgets,
  });
  const chunks = toChunks(await response.text());
  return { response, chunks, lines, events, urls: fake.urls, closings: () => closings };
}

describe("runChat on REST · no auth", () => {
  it("streams both tool calls, with their records, then the answer", async () => {
    const { response, chunks, urls } = await runTurn(parisModel(), [
      { fixture: "geocode-paris" },
      { fixture: "forecast-paris" },
    ]);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(urls).toHaveLength(2);
    expect(chunks[0]).toMatchObject({ type: "start", messageMetadata: { createdAt: NOW.getTime() } });
    const outputs = chunks.filter((chunk) => chunk.type === "tool-output-available");
    expect(outputs.map((chunk) => chunk.toolCallId)).toEqual(["call-1", "call-2"]);
    expect(outputs[0].output).toMatchObject({
      summary: "Paris, Île-de-France Region, FR · 48.85, 2.35",
      result: { isAmbiguous: false },
      call: { laneId: "rest-no-auth", cache: "miss", wire: { method: "GET", url: urls[0] } },
    });
    expect(outputs[1].output.result).toMatchObject({ timeZone: "Europe/Paris", fetchedAt: NOW.toISOString() });
    expect(outputs[1].output.call.wire.url).toContain("timezone=auto");
    const text = chunks.filter((chunk) => chunk.type === "text-delta").map((chunk) => chunk.delta);
    expect(text.join("")).toBe(ANSWER);
    expect(chunks.at(-1)).toMatchObject({ type: "finish" });
  });

  it("gives the model the system prompt and the four tools, and only the weather from each result", async () => {
    const model = parisModel();
    await runTurn(model, [{ fixture: "geocode-paris" }, { fixture: "forecast-paris" }]);
    const [first, second] = model.doStreamCalls;
    expect(first?.prompt[0]).toMatchObject({ role: "system" });
    expect(JSON.stringify(first?.prompt[0])).toContain("The time now is 2026-10-29T16:00:00.000Z (UTC)");
    expect(first?.tools?.map((tool) => tool.name).sort()).toEqual([
      "geocode_location",
      "get_air_quality",
      "get_current_weather",
      "get_forecast",
    ]);
    const toolMessage = second?.prompt.find((message) => message.role === "tool");
    const sent = JSON.stringify(toolMessage);
    expect(sent).toContain("Île-de-France Region");
    expect(sent).not.toContain("geocoding-api.open-meteo.com");
    expect(sent).not.toContain("durationMs");
  });

  it("logs each tool call, each model step, then the answer's end: time, steps, tool calls and tokens", async () => {
    const { response, events, lines } = await runTurn(parisModel(), [
      { fixture: "geocode-paris" },
      { fixture: "forecast-paris" },
    ]);
    expect(response.headers.get("x-request-id")).toBe(REQUEST_ID);
    expect(events()).toEqual([
      "info upstream.http",
      "info tool.call",
      "info model.step",
      "info upstream.http",
      "info tool.call",
      "info model.step",
      "info model.step",
      "info chat.done",
    ]);
    expect(lines.find((line) => line.event === "tool.call")).toMatchObject({
      tool: "geocode_location",
      status: "ok",
      cache: "miss",
      ms: expect.any(Number),
    });
    expect(lines.find((line) => line.event === "model.step")).toMatchObject({
      step: 0,
      model: "mock-model-id",
      finishReason: "tool-calls",
      inputTokens: 10,
      outputTokens: 5,
      toolCalls: 1,
    });
    expect(lines.at(-1)).toMatchObject({
      event: "chat.done",
      steps: 3,
      toolCalls: 2,
      inputTokens: 30,
      outputTokens: 15,
      finishReason: "stop",
    });
  });

  it("streams a failed tool call to the page as our sentence, without Open-Meteo's own text", async () => {
    const fail = () => new Response("upstream says: internal details", { status: 503 });
    const { chunks } = await runTurn(parisModel(), [fail, fail, { fixture: "forecast-paris" }]);
    const failed = chunks.find((chunk) => chunk.type === "tool-output-error");
    expect(failed).toMatchObject({
      toolCallId: "call-1",
      errorText: "The weather service can't be reached right now. Please try again in a minute.",
    });
    expect(JSON.stringify(chunks)).not.toContain("internal details");
  });

  it("lets the last of its 5 steps only write, so an answer never ends on tool calls alone", async () => {
    const geocode = (n: number) => step([toolCall(`call-${n}`, "geocode_location", { query: "Paris" })], "tool-calls");
    const answer = textStep(ANSWER);
    const model = new MockLanguageModelV4({ doStream: [geocode(1), geocode(2), geocode(3), geocode(4), answer] });
    await runTurn(model, [{ fixture: "geocode-paris" }]);
    expect(model.doStreamCalls).toHaveLength(5);
    expect(model.doStreamCalls[3]?.toolChoice).not.toEqual({ type: "none" });
    expect(model.doStreamCalls[4]?.toolChoice).toEqual({ type: "none" });
  });

  it("marks an answer a time budget cut short, so the page can say so, logs it, and closes the lane", async () => {
    const silent = { stream: new ReadableStream<LanguageModelV4StreamPart>({ start: () => undefined }) };
    const model = new MockLanguageModelV4({ doStream: [silent] });
    const { chunks, events, closings } = await runTurn(model, [], { totalMs: 60_000, firstChunkMs: 50, toolMs: 8000 });
    expect(chunks).toContainEqual({
      type: "message-metadata",
      messageMetadata: { createdAt: NOW.getTime(), isCutShort: true },
    });
    expect(events()).toEqual(["warn budget.exceeded"]);
    expect(closings()).toBe(1);
  });

  it("logs Gemini's failure as a ModelError, gives the page our sentence and ref, and closes the lane", async () => {
    const model = new MockLanguageModelV4({
      doStream: async () => {
        throw new APICallError({
          message: "API key not valid. Please pass a valid API key.",
          url: "https://generativelanguage.googleapis.com/v1beta/models/gemini:streamGenerateContent",
          requestBodyValues: {},
          statusCode: 400,
        });
      },
    });
    const { chunks, lines, events, closings } = await runTurn(model, []);
    expect(chunks).toContainEqual({
      type: "error",
      errorText: "The assistant didn't answer. Please try again. (ref b1a0d9e8)",
    });
    expect(events()).toEqual(["error chat.failed"]);
    expect(lines[0]).toMatchObject({
      status: "failed",
      errorClass: "ModelError",
      message: "API key not valid. Please pass a valid API key.",
      isRetryable: true,
      causeClass: "AI_APICallError",
    });
    expect(closings()).toBe(1);
  });
});

describe("runChat, when the model fails after a finished step", () => {
  it("ends the answer once, with chat.failed, and no chat.done after it", async () => {
    // The first call asks for a tool; the second fails as Gemini does, with an HTTP error AI SDK doesn't retry.
    let calls = 0;
    const model = new MockLanguageModelV4({
      doStream: async () => {
        calls += 1;
        if (calls === 1) {
          return step([toolCall("call-1", "geocode_location", { query: "Paris" })], "tool-calls");
        }
        throw new APICallError({
          message: "API key expired. Please renew the API key.",
          url: "https://generativelanguage.googleapis.com/v1beta/models/gemini:streamGenerateContent",
          requestBodyValues: {},
          statusCode: 400,
        });
      },
    });
    const { events, lines } = await runTurn(model, [{ fixture: "geocode-paris" }]);
    expect(events()).toEqual(["info upstream.http", "info tool.call", "info model.step", "error chat.failed"]);
    expect(lines.at(-1)).toMatchObject({ errorClass: "ModelError", causeClass: "AI_APICallError" });
  });
});

describe("runChat through MCP · no auth", () => {
  it("streams the same answer, each chip with its lane and the tools/call request it really sent", async () => {
    const server = createMcpServerFetch([{ fixture: "geocode-paris" }, { fixture: "forecast-paris" }]);
    const { log } = createTestLog();
    const lane = await openMcpNoAuthLane({ origin: TEST_ORIGIN, requestId: REQUEST_ID, log, fetch: server.fetch });
    const signal = new AbortController().signal;
    const response = await runChat(
      { ...CHAT_REQUEST, laneId: "mcp-no-auth" },
      { model: parisModel(), lane, signal, requestId: REQUEST_ID, log, now: () => NOW },
    );
    const chunks = toChunks(await response.text());
    const outputs = chunks.filter((chunk) => chunk.type === "tool-output-available");
    expect(outputs.map((chunk) => chunk.output.call.laneId)).toEqual(["mcp-no-auth", "mcp-no-auth"]);
    expect(outputs.map((chunk) => JSON.parse(chunk.output.call.wire.body).params.name)).toEqual([
      "geocode_location",
      "get_forecast",
    ]);
    expect(outputs[0].output.summary).toBe("Paris, Île-de-France Region, FR · 48.85, 2.35");
    expect(outputs[1].output.result).toMatchObject({ timeZone: "Europe/Paris" });
    const text = chunks.filter((chunk) => chunk.type === "text-delta").map((chunk) => chunk.delta);
    expect(text.join("")).toBe(ANSWER);
  });
});

describe("runChat after the chat changes lanes", () => {
  it("still gives the model only the weather from a result whose tool the new lane doesn't have", async () => {
    // A get_forecast result from REST · no auth, then a question on REST · with auth, which has no get_forecast.
    const earlier = {
      id: "a1",
      role: "assistant",
      parts: [
        {
          type: "tool-get_forecast",
          toolCallId: "c1",
          state: "output-available",
          input: { latitude: 48.85, longitude: 2.35, days: 2, includeHourly: false, units: "metric" },
          output: {
            result: { timeZone: "Europe/Paris", days: [] },
            summary: "2 days · 6 to 16 °C · rain up to 0%",
            call: {
              laneId: "rest-no-auth",
              cache: "miss",
              durationMs: 412,
              wire: { method: "GET", url: "https://api.open-meteo.com/v1/forecast?latitude=48.85", headers: {} },
            },
          },
        },
      ],
      metadata: { createdAt: NOW.getTime() },
    };
    const chatRequest = await parseChatRequest(
      {
        ...CHAT_REQUEST,
        id: "chat-1",
        laneId: "rest-auth",
        messages: [...CHAT_REQUEST.messages, earlier, { ...CHAT_REQUEST.messages[0], id: "u2" }],
      },
      LIVE_LANE_IDS,
    );
    const { log } = createTestLog();
    const lane = openRestAuthLane({
      token: "test-token-not-real",
      requestId: REQUEST_ID,
      log,
      apify: createApifyClient({ token: "test-token-not-real", fetch: createApifyFetch([]).fetch }),
      openMeteo: createOpenMeteoClient({
        fetch: createFakeFetch([]).fetch,
        cache: createMemoryCache(),
        random: () => 0,
      }),
    });
    const model = new MockLanguageModelV4({ doStream: [textStep(ANSWER)] });
    const response = await runChat(chatRequest, {
      model,
      lane,
      signal: new AbortController().signal,
      requestId: REQUEST_ID,
      log,
      now: () => NOW,
    });
    await response.text();
    const sent = JSON.stringify(model.doStreamCalls[0]?.prompt.find((message) => message.role === "tool"));
    expect(sent).toContain("Europe/Paris");
    expect(sent).not.toContain("api.open-meteo.com");
    expect(sent).not.toContain("durationMs");
  });
});
