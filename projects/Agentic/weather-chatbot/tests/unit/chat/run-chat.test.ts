/*
 * tests/unit/chat/run-chat.test.ts: one whole chat turn, on REST · no auth and through MCP · no auth, with AI SDK's
 * mock model in place of Gemini and Open-Meteo's recorded answers in place of the network: what the page receives,
 * and what the model reads.
 */
import type { LanguageModelV4StreamPart } from "@ai-sdk/provider";
import { MockLanguageModelV4 } from "ai/test";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatRequest } from "@/lib/chat/chat-request";
import { type AnswerBudgets, runChat } from "@/lib/chat/run-chat";
import { openMcpNoAuthLane } from "@/lib/lanes/mcp-no-auth";
import { openRestNoAuthLane } from "@/lib/lanes/rest-no-auth";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import { createFakeFetch, createMemoryCache, type FakeAnswer } from "@/tests/stubs/open-meteo-stand-ins";

const NOW = new Date("2026-10-29T16:00:00Z");
const QUESTION = "Do I need an umbrella in Paris tomorrow afternoon?";
const ANSWER = "No umbrella needed: a 0% chance of rain all afternoon.";
const USAGE = {
  inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 5, text: 5, reasoning: 0 },
};

/** One model step: it streams these parts, then finishes for the given reason. */
function step(parts: LanguageModelV4StreamPart[], reason: "tool-calls" | "stop") {
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
function toolCall(toolCallId: string, toolName: string, input: unknown): LanguageModelV4StreamPart {
  return { type: "tool-call", toolCallId, toolName, input: JSON.stringify(input) };
}

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
      step(
        [
          { type: "text-start", id: "text-1" },
          { type: "text-delta", id: "text-1", delta: ANSWER },
          { type: "text-end", id: "text-1" },
        ],
        "stop",
      ),
    ],
  });
}

const CHAT_REQUEST: ChatRequest = {
  laneId: "rest-no-auth",
  locale: "en-GB",
  messages: [
    { id: "u1", role: "user", parts: [{ type: "text", text: QUESTION }], metadata: { createdAt: NOW.getTime() } },
  ],
};

/** Runs one turn: the UI message stream's chunks as the page receives them, and how often the lane was closed. */
async function runTurn(model: MockLanguageModelV4, answers: FakeAnswer[], budgets?: AnswerBudgets) {
  const fake = createFakeFetch(answers);
  const openMeteo = createOpenMeteoClient({
    fetch: fake.fetch,
    cache: createMemoryCache(),
    now: () => NOW,
    random: () => 0,
  });
  let closings = 0;
  const lane = {
    ...openRestNoAuthLane({ openMeteo }),
    close: async () => {
      closings += 1;
    },
  };
  const signal = new AbortController().signal;
  const response = await runChat(CHAT_REQUEST, { model, lane, signal, now: () => NOW, budgets });
  const chunks = toChunks(await response.text());
  return { response, chunks, urls: fake.urls, closings: () => closings };
}

/** A UI message stream's chunks, from its response body: one `data:` line each, then `[DONE]`. */
function toChunks(body: string) {
  return body
    .split("\n")
    .filter((line) => line.startsWith("data: ") && line !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)));
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
    const answer = step(
      [
        { type: "text-start", id: "text-1" },
        { type: "text-delta", id: "text-1", delta: ANSWER },
        { type: "text-end", id: "text-1" },
      ],
      "stop",
    );
    const model = new MockLanguageModelV4({ doStream: [geocode(1), geocode(2), geocode(3), geocode(4), answer] });
    await runTurn(model, [{ fixture: "geocode-paris" }]);
    expect(model.doStreamCalls).toHaveLength(5);
    expect(model.doStreamCalls[3]?.toolChoice).not.toEqual({ type: "none" });
    expect(model.doStreamCalls[4]?.toolChoice).toEqual({ type: "none" });
  });

  it("marks an answer a time budget cut short, so the page can say so, and closes the lane", async () => {
    const silent = { stream: new ReadableStream<LanguageModelV4StreamPart>({ start: () => undefined }) };
    const model = new MockLanguageModelV4({ doStream: [silent] });
    const { chunks, closings } = await runTurn(model, [], { totalMs: 60_000, firstChunkMs: 50, toolMs: 8000 });
    expect(chunks).toContainEqual({
      type: "message-metadata",
      messageMetadata: { createdAt: NOW.getTime(), isCutShort: true },
    });
    expect(closings()).toBe(1);
  });

  it("logs a model failure, gives the page only our sentence, and closes the lane", async () => {
    const written = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const model = new MockLanguageModelV4({
      doStream: async () => {
        throw new Error("API key not valid. Please pass a valid API key.");
      },
    });
    const { chunks, closings } = await runTurn(model, []);
    expect(chunks).toContainEqual({ type: "error", errorText: "The assistant didn't answer. Please try again." });
    const logged = written.mock.calls.map((call) => JSON.parse(String(call[0])));
    expect(logged).toContainEqual({
      level: "error",
      event: "chat.failed",
      lane: "rest-no-auth",
      errorClass: "Error",
      message: "API key not valid. Please pass a valid API key.",
    });
    expect(closings()).toBe(1);
  });
});

describe("runChat through MCP · no auth", () => {
  it("streams the same answer, each chip with its lane and the tools/call request it really sent", async () => {
    const server = createMcpServerFetch([{ fixture: "geocode-paris" }, { fixture: "forecast-paris" }]);
    const lane = await openMcpNoAuthLane({ origin: TEST_ORIGIN, fetch: server.fetch });
    const signal = new AbortController().signal;
    const response = await runChat(
      { ...CHAT_REQUEST, laneId: "mcp-no-auth" },
      { model: parisModel(), lane, signal, now: () => NOW },
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

afterEach(() => {
  vi.restoreAllMocks();
});
