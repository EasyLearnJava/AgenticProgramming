/*
 * tests/evals/golden.eval.ts: the golden questions (PLAN.md section 10), asked of a running deployment, so its real
 * model answers, on each live lane in EVAL_LANES (both no-auth lanes if it's not set). Each says which tools must be
 * called, and what the answer must and mustn't do. They run only with EVAL_BASE_URL set (the deployment uses its own
 * GOOGLE_API_KEY), one question at a time.
 */
import { describe, expect, it } from "vitest";
import { addDays, toLocalDateTime, toWeekday } from "@/lib/utils";

const BASE_URL = process.env.EVAL_BASE_URL;
const BYPASS_SECRET = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
const LANES = (process.env.EVAL_LANES ?? "rest-no-auth,mcp-no-auth").split(",").map((lane) => lane.trim());
// Each question makes two or three model calls in a few seconds; a 15 s pause before each next one keeps a run near
// 10 model calls a minute, inside Gemini's free-tier rate.
const PAUSE_BETWEEN_QUESTIONS_MS = 15_000;

type ToolCall = { toolName: string; input: Record<string, unknown> };
type Answer = { toolCalls: ToolCall[]; outputs: Record<string, unknown>[]; text: string; errors: string[] };

let questionsAsked = 0;

/**
 * Asks one question on a lane, as a browser in this time zone would, if one is given, and reads the streamed answer:
 * the tool calls, their outputs, and the text.
 */
async function ask(question: string, laneId: string, timeZone?: string): Promise<Answer> {
  if (questionsAsked > 0) {
    await new Promise((resolve) => setTimeout(resolve, PAUSE_BETWEEN_QUESTIONS_MS));
  }
  questionsAsked += 1;
  const response = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(BYPASS_SECRET ? { "x-vercel-protection-bypass": BYPASS_SECRET } : {}),
    },
    body: JSON.stringify({
      id: `eval-${Date.now()}`,
      laneId,
      locale: "en-GB",
      ...(timeZone ? { timeZone } : {}),
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
  const outputs = chunks.filter((chunk) => chunk.type === "tool-output-available").map((chunk) => chunk.output);
  // Every tool call went through the lane asked for.
  expect(outputs.map((output) => output.call.laneId)).toEqual(outputs.map(() => laneId));
  return {
    toolCalls: chunks.filter((chunk) => chunk.type === "tool-input-available"),
    outputs: outputs.map((output) => output.result),
    text: chunks
      .filter((chunk) => chunk.type === "text-delta")
      .map((chunk) => chunk.delta)
      .join(""),
    errors: chunks
      .filter((chunk) => chunk.type === "error" || chunk.type === "tool-output-error")
      .map((chunk) => chunk.errorText),
  };
}

/**
 * A user's time zone whose date isn't UTC's right now, so an answer that read "tomorrow" by the UTC date would name
 * the wrong day, and that is at least an hour from its own midnight, so its date holds while the question is asked:
 * Pago Pago (UTC−11) before 10:00 UTC, a day behind UTC; Kiritimati (UTC+14) from then on, a day ahead.
 */
function toZoneOffUtcDate(): string {
  return new Date().getUTCHours() < 10 ? "Pacific/Pago_Pago" : "Pacific/Kiritimati";
}

/**
 * Tomorrow in a time zone, on this machine's clock, as an answer may name it: "Friday", "October 30" or "30 October".
 */
function toTomorrowPattern(timeZone: string): RegExp {
  const [today = ""] = toLocalDateTime(new Date().toISOString(), timeZone).split("T");
  const tomorrow = addDays(today, 1);
  const date = new Date(`${tomorrow}T00:00:00Z`);
  const month = date.toLocaleString("en-US", { month: "long", timeZone: "UTC" });
  const day = date.getUTCDate();
  return new RegExp(`${toWeekday(tomorrow)}|${month} ${day}\\b|\\b${day} ${month}|${month.slice(0, 3)} ${day}\\b`);
}

/** The tools an answer called, by name, in order. */
function toolNames(answer: Answer): string[] {
  return answer.toolCalls.map((call) => call.toolName);
}

const WEATHER_TOOLS = ["get_current_weather", "get_forecast", "get_air_quality"];

describe.skipIf(!BASE_URL)(`the golden questions at ${BASE_URL ?? "(EVAL_BASE_URL not set)"}`, () => {
  for (const laneId of LANES) {
    describe(`on ${laneId}`, () => {
      it("“What's the weather in Tokyo right now?”: geocoding, then the weather now, with numbers", async () => {
        const answer = await ask("What's the weather in Tokyo right now?", laneId);
        expect(answer.errors).toEqual([]);
        expect(toolNames(answer)).toEqual(["geocode_location", "get_current_weather"]);
        expect(answer.text).toMatch(/Tokyo/);
        // Grounded (PLAN.md section 8): the tool's temperature, as it is or rounded, is in the answer.
        const temperature = answer.outputs[1]?.temperature;
        expect(typeof temperature).toBe("number");
        const written = [String(temperature), String(Math.round(temperature as number))];
        expect(
          written.some((value) => answer.text.includes(value)),
          answer.text,
        ).toBe(true);
      });

      it("“Do I need an umbrella in Paris tomorrow afternoon?”: an hourly forecast for Paris, France", async () => {
        const answer = await ask("Do I need an umbrella in Paris tomorrow afternoon?", laneId);
        expect(answer.errors).toEqual([]);
        expect(toolNames(answer)).toEqual(["geocode_location", "get_forecast"]);
        expect(answer.toolCalls[1]?.input.includeHourly).toBe(true);
        expect(answer.text).toMatch(/Paris/);
        expect(answer.text).toMatch(/umbrella|rain/i);
      });

      // "Tomorrow" is the user's tomorrow, wherever the place is (issue 87). Asked from a time zone whose date isn't
      // UTC's, an answer that took tomorrow from the UTC date, or from the place's, would name another day.
      it("“Will it rain in Dallas, Texas tomorrow?”, from off UTC's date: names the user's tomorrow", async () => {
        const timeZone = toZoneOffUtcDate();
        const tomorrow = toTomorrowPattern(timeZone);
        const answer = await ask("Will it rain in Dallas, Texas tomorrow?", laneId, timeZone);
        expect(answer.errors).toEqual([]);
        expect(answer.text).toMatch(tomorrow);
      });

      it("“Will it rain in Paris tomorrow?”, from off UTC's date: the user's tomorrow, not Paris's", async () => {
        const timeZone = toZoneOffUtcDate();
        const tomorrow = toTomorrowPattern(timeZone);
        const answer = await ask("Will it rain in Paris tomorrow?", laneId, timeZone);
        expect(answer.errors).toEqual([]);
        expect(answer.text).toMatch(tomorrow);
      });

      it("“What's the weather in Springfield?”: asks which Springfield, and fetches no weather", async () => {
        const answer = await ask("What's the weather in Springfield?", laneId);
        expect(toolNames(answer)).toContain("geocode_location");
        expect(toolNames(answer).filter((name) => WEATHER_TOOLS.includes(name))).toEqual([]);
        const regions = ["Missouri", "Massachusetts", "Illinois"].filter((region) => answer.text.includes(region));
        expect(regions.length, answer.text).toBeGreaterThanOrEqual(2);
      });

      it("“What's the weather in Hogwarts?”: says it can't find the place, and fetches no weather", async () => {
        const answer = await ask("What's the weather in Hogwarts?", laneId);
        expect(toolNames(answer)).toContain("geocode_location");
        expect(toolNames(answer).filter((name) => WEATHER_TOOLS.includes(name))).toEqual([]);
        expect(answer.text).toMatch(/(couldn't|could not|can't|cannot|unable to|didn't|did not) (find|locate)/i);
      });

      it("“Write me a poem about the sea.”: one sentence on what it does, and no tools", async () => {
        const answer = await ask("Write me a poem about the sea.", laneId);
        expect(toolNames(answer)).toEqual([]);
        expect(answer.text).toMatch(/weather/i);
        expect(answer.text.length, answer.text).toBeLessThan(400);
      });
    });
  }
});
