/*
 * lib/types.ts: the types the page and the server share.
 */

/** The four lanes: the door (REST or MCP), then the auth. */
export type LaneId = "rest-no-auth" | "rest-auth" | "mcp-no-auth" | "mcp-auth";

/** One lane, as the page describes it. */
export type LaneInfo = {
  id: LaneId;
  transport: "rest" | "mcp";
  auth: "none" | "bearer";
  label: string;
  door: string;
  builtInStep: number;
};

/** An HTTP request exactly as it goes out: what a tool chip's wire view shows. */
export type WireRequest = {
  method: "GET" | "POST";
  url: string;
  headers: Readonly<Record<string, string>>;
  body?: string;
};

/** One tool call, as a chip shows it, for the lane it went through. (Running and failed calls, and times, come in step 3.) */
export type ToolCallView = {
  id: string;
  tool: string;
  laneId: LaneId;
  inputSummary: string;
  resultSummary: string;
  input: unknown;
  output: unknown;
  wire: WireRequest;
};

/** The chance of rain in one hour, for the weather card's bars. */
export type HourlyRain = { hour: string; chancePercent: number };

/** What the weather card shows, already worded for the page. */
export type ForecastView = {
  place: string;
  period: string;
  condition: string;
  temperatureRange: string;
  sunset: string;
  hourlyRain: readonly HourlyRain[];
  fetched: string;
};

/** One message in the conversation, with the tool calls it made and its weather card. */
export type MessageView = {
  id: string;
  role: "user" | "bot";
  time: string;
  text: string;
  toolCalls?: readonly ToolCallView[];
  forecast?: ForecastView;
};

/** One cell of the compare view: the same call, through one lane. */
export type CompareCell = { lane: LaneInfo; tool: string; wire: WireRequest };
