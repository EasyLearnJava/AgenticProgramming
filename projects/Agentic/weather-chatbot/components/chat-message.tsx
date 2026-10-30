/*
 * components/chat-message.tsx: one message: who and when, the tool calls it made (as chips), its text, and a weather
 * card for each forecast it got.
 */
import { type DynamicToolUIPart, getToolName, isToolUIPart, type ToolUIPart } from "ai";
import type { ReactNode } from "react";
import { AnswerMarkdown } from "@/components/answer-markdown";
import { ToolChip } from "@/components/tool-chip";
import { WeatherCard } from "@/components/weather-card";
import { ACTOR_TOOL_NAME } from "@/lib/constants";
import type { ChatMessage as ChatMessageData, Forecast, Place, ToolCallView, WeatherToolTypes } from "@/lib/types";
import { roundCoordinate } from "@/lib/utils";

type ChatMessageProps = { message: ChatMessageData; isAnswering: boolean };
type WeatherToolPart = ToolUIPart<WeatherToolTypes>;
// A tool the page doesn't know by name (an MCP server may add one); its chip shows its input and output as they are.
type AnyToolPart = WeatherToolPart | DynamicToolUIPart;

// A place geocoding found counts as the forecast's place when it's this close, in degrees.
const SAME_PLACE_DEGREES = 0.05;
// The tools whose result is a forecast: ours, and the auth lanes' Actor tool.
const FORECAST_PART_TYPES: ReadonlySet<string> = new Set(["tool-get_forecast", `tool-${ACTOR_TOOL_NAME}`]);

/** A short form of a tool's input, for its chip: "“Paris”", or "48.85, 2.35 · 2 days, hourly". */
function toInputSummary(input: unknown): string {
  if (typeof input !== "object" || input === null) {
    return "";
  }
  const fields: Record<string, unknown> = { ...input };
  if (typeof fields.query === "string") {
    return `“${fields.query}”`;
  }
  // The Actor tool's input: its one location's name and coordinates, its days, and its mode.
  if (Array.isArray(fields.locations) && typeof fields.locations[0] === "object" && fields.locations[0] !== null) {
    const { forecastDays, mode, units } = fields;
    return toInputSummary({ ...fields.locations[0], days: forecastDays, includeHourly: mode === "hourly", units });
  }
  const parts: string[] = [];
  if (typeof fields.latitude === "number" && typeof fields.longitude === "number") {
    parts.push(`${roundCoordinate(fields.latitude)}, ${roundCoordinate(fields.longitude)}`);
  }
  if (typeof fields.days === "number") {
    parts.push(
      `${fields.days} ${fields.days === 1 ? "day" : "days"}${fields.includeHourly === true ? ", hourly" : ""}`,
    );
  }
  if (fields.units === "imperial") {
    parts.push("°F");
  }
  return parts.join(" · ");
}

/** A tool call, in the shape its chip shows; one still running when its answer has ended was stopped. */
function toToolCallView(part: AnyToolPart, isAnswering: boolean): ToolCallView {
  const base = {
    id: part.toolCallId,
    tool: getToolName(part),
    input: part.input,
    inputSummary: toInputSummary(part.input),
  };
  switch (part.state) {
    case "output-available":
      return part.type === "dynamic-tool"
        ? { ...base, status: "done", output: part.output }
        : {
            ...base,
            status: "done",
            resultSummary: part.output.summary,
            output: part.output.result,
            call: part.output.call,
            fallback: part.output.fallback,
          };
    case "output-error":
      return { ...base, status: "failed", errorText: part.errorText };
    case "output-denied":
      return { ...base, status: "failed", errorText: "The call was refused." };
    default:
      return { ...base, status: isAnswering ? "running" : "stopped" };
  }
}

/** The forecasts a message got, each with the place geocoding found at its coordinates, if any. */
function toForecasts(parts: readonly AnyToolPart[]): { forecast: Forecast; placeName: string | undefined }[] {
  const places: Place[] = parts.flatMap((part) =>
    part.type === "tool-geocode_location" && part.state === "output-available" ? part.output.result.candidates : [],
  );
  return parts.flatMap((part) => {
    if (!FORECAST_PART_TYPES.has(part.type) || part.state !== "output-available") {
      return [];
    }
    const forecast = (part.output as { result: Forecast }).result;
    const place = places.find(
      (candidate) =>
        Math.abs(candidate.latitude - forecast.latitude) <= SAME_PLACE_DEGREES &&
        Math.abs(candidate.longitude - forecast.longitude) <= SAME_PLACE_DEGREES,
    );
    const placeName = place ? [place.name, place.region, place.country].filter(Boolean).join(", ") : undefined;
    return [{ forecast, placeName }];
  });
}

/** When a message was written, on this browser's clock: "17:00". */
function toClockTime(createdAt: number | undefined): string {
  return createdAt === undefined
    ? ""
    : new Date(createdAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** One message of the conversation: the bot's on the left, yours on the right. */
export function ChatMessage({ message, isAnswering }: ChatMessageProps): ReactNode {
  const isBot = message.role === "assistant";
  const toolParts: AnyToolPart[] = message.parts.filter(isToolUIPart);
  const text = message.parts.map((part) => (part.type === "text" ? part.text : "")).join("");
  return (
    <li className={`message message-${isBot ? "bot" : "user"}`}>
      <p className="message-meta">
        {isBot ? (
          <span className="avatar" aria-hidden="true">
            N
          </span>
        ) : null}
        <span>{isBot ? "Nimbus (Weather)" : "You"}</span>
        <span aria-hidden="true">·</span>
        <time>{toClockTime(message.metadata?.createdAt)}</time>
      </p>
      {toolParts.length > 0 ? (
        <div className="tool-chips">
          {toolParts.map((part) => (
            <ToolChip key={part.toolCallId} call={toToolCallView(part, isAnswering)} />
          ))}
        </div>
      ) : null}
      {text === "" ? null : isBot ? (
        <div className="bubble bubble-bot">
          <AnswerMarkdown text={text} />
        </div>
      ) : (
        <p className="bubble bubble-user">{text}</p>
      )}
      {message.metadata?.isCutShort ? (
        <p className="message-note" role="status">
          This answer was cut short: it took longer than the time allowed. Please ask again.
        </p>
      ) : null}
      {toForecasts(toolParts).map(({ forecast, placeName }) => (
        <WeatherCard
          key={`${forecast.latitude},${forecast.longitude},${forecast.days.length}`}
          forecast={forecast}
          placeName={placeName}
        />
      ))}
    </li>
  );
}
