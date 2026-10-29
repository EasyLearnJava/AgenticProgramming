/*
 * tests/evals/golden.eval.ts: the golden questions (PLAN.md section 10), asked of a running deployment, so its real
 * model answers through REST · no auth. Each says which tools must be called, and what the answer must and mustn't do.
 * They run only with EVAL_BASE_URL set (the deployment uses its own GOOGLE_API_KEY), one question at a time.
 */
import { describe, expect, it } from "vitest";

const BASE_URL = process.env.EVAL_BASE_URL;
const BYPASS_SECRET = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
// Each question makes two or three model calls in a few seconds; a 15 s pause after each keeps a run near 10 model
// calls a minute, inside Gemini's free-tier rate.
const PAUSE_BETWEEN_QUESTIONS_MS = 15_000;

type ToolCall = { toolName: string; input: Record<string, unknown> };
type Answer = { toolCalls: ToolCall[]; outputs: Record<string, unknown>[]; text: string; errors: string[] };

/** Asks one question on REST · no auth, and reads the streamed answer: the tool calls, their outputs, and the text. */
async function ask(question: string): Promise<Answer> {
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(BYPASS_SECRET ? { "x-vercel-protection-bypass": BYPASS_SECRET } : {}),
    },
    body: JSON.stringify({
      id: `eval-${Date.now()}`,
      laneId: "rest-no-auth",
      locale: "en-GB",
      messages: [
        { id: "q1", role: "user", parts: [{ type: "text", text: question }], metadata: { createdAt: Date.now() } },
      ],
    }),
  });
  const body = await response.text();
  expect(response.status, body).toBe(200);
  const chunks = body
    .split("\n")
    .filter((line) => line.startsWith("data: ") && line !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)));
  return {
    toolCalls: chunks.filter((chunk) => chunk.type === "tool-input-available"),
    outputs: chunks.filter((chunk) => chunk.type === "tool-output-available").map((chunk) => chunk.output.result),
    text: chunks
      .filter((chunk) => chunk.type === "text-delta")
      .map((chunk) => chunk.delta)
      .join(""),
    errors: chunks
      .filter((chunk) => chunk.type === "error" || chunk.type === "tool-output-error")
      .map((c) => c.errorText),
  };
}

/** The tools an answer called, by name, in order. */
function toolNames(answer: Answer): string[] {
  return answer.toolCalls.map((call) => call.toolName);
}

const WEATHER_TOOLS = ["get_current_weather", "get_forecast", "get_air_quality"];

describe.skipIf(!BASE_URL)(
  `the golden questions, on REST · no auth at ${BASE_URL ?? "(EVAL_BASE_URL not set)"}`,
  () => {
    it("“What's the weather in Tokyo right now?”: geocoding, then the weather now; names Tokyo, with its numbers", async () => {
      const answer = await ask("What's the weather in Tokyo right now?");
      expect(answer.errors).toEqual([]);
      expect(toolNames(answer)).toEqual(["geocode_location", "get_current_weather"]);
      expect(answer.text).toMatch(/Tokyo/);
      const temperature = answer.outputs[1]?.temperature;
      expect(typeof temperature).toBe("number");
      expect(answer.text).toContain(String(Math.round(temperature as number)));
    });

    it("“Do I need an umbrella in Paris tomorrow afternoon?”: an hourly forecast for Paris, France", async () => {
      await pause();
      const answer = await ask("Do I need an umbrella in Paris tomorrow afternoon?");
      expect(answer.errors).toEqual([]);
      expect(toolNames(answer)).toEqual(["geocode_location", "get_forecast"]);
      expect(answer.toolCalls[1]?.input.includeHourly).toBe(true);
      expect(answer.text).toMatch(/Paris/);
      expect(answer.text).toMatch(/umbrella|rain/i);
    });

    it("“What's the weather in Springfield?”: asks which Springfield, and fetches no weather", async () => {
      await pause();
      const answer = await ask("What's the weather in Springfield?");
      expect(toolNames(answer)).toContain("geocode_location");
      expect(toolNames(answer).filter((name) => WEATHER_TOOLS.includes(name))).toEqual([]);
      const regions = ["Missouri", "Massachusetts", "Illinois"].filter((region) => answer.text.includes(region));
      expect(regions.length, answer.text).toBeGreaterThanOrEqual(2);
    });

    it("“What's the weather in Hogwarts?”: says it can't find the place, and fetches no weather", async () => {
      await pause();
      const answer = await ask("What's the weather in Hogwarts?");
      expect(toolNames(answer)).toContain("geocode_location");
      expect(toolNames(answer).filter((name) => WEATHER_TOOLS.includes(name))).toEqual([]);
      expect(answer.text).toMatch(/(couldn't|could not|can't|cannot|unable to|didn't|did not) (find|locate)/i);
    });

    it("“Write me a poem about the sea.”: one sentence on what it does, and no tools", async () => {
      await pause();
      const answer = await ask("Write me a poem about the sea.");
      expect(toolNames(answer)).toEqual([]);
      expect(answer.text).toMatch(/weather/i);
      expect(answer.text.length, answer.text).toBeLessThan(400);
    });
  },
);

/** Waits between questions, to stay inside Gemini's free-tier rate. */
function pause(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, PAUSE_BETWEEN_QUESTIONS_MS));
}
