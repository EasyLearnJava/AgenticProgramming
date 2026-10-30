/*
 * tests/stubs/apify-stand-ins.ts: what the Apify clients get in the tests instead of the network. For the REST door, a
 * fetch that answers from tests/fixtures/apify/ and records each request it was given; for the MCP door, a stand-in
 * for Apify's MCP server as AI SDK's MCP client sees it, and a fetch that gives Apify MCP's real 401. The fixtures are
 * real: Apify's answers to a fake token or none (PLAN.md section 3, rows 2 and 13), and the Actor's answers for Dallas
 * from the live check on 29 October 2026 (build 1.0.9): 3 days in daily mode (run YkHk86C21n7Ze4FJI) and 1 day in
 * hourly mode (run hqYzy1J0NhcCENCeX), copied from the runs' output in Apify Console. The MCP server's run answer is
 * shaped as its source declares it (RunResponse, in src/tools/actors/actor_run_response.ts of apify/apify-mcp-server).
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import type { CallToolResult, MCPClientConfig } from "@ai-sdk/mcp";
import type { McpClient } from "@/lib/types";

const FIXTURES_DIR = path.join(import.meta.dirname, "..", "fixtures", "apify");

/** One answer the fake fetch gives: a fixture's name with its status, or a function for anything else. */
export type ApifyAnswer = { fixture: string; status: number } | (() => Response);

/** One request the fake fetch was given: its address, method, headers and body. */
export type SentRequest = { url: string; method: string; headers: Record<string, string>; body: string };

/** A fetch that gives the answers in order, one per call, and records every request. */
export function createApifyFetch(answers: ApifyAnswer[]): { fetch: typeof fetch; requests: SentRequest[] } {
  const requests: SentRequest[] = [];
  const fakeFetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    requests.push({
      url: String(input),
      method: init?.method ?? "GET",
      headers: Object.fromEntries(new Headers(init?.headers).entries()),
      body: typeof init?.body === "string" ? init.body : "",
    });
    const answer = answers[requests.length - 1];
    if (answer === undefined) {
      throw new Error(`The fake Apify fetch has no answer for call ${requests.length}: ${String(input)}`);
    }
    if (typeof answer === "function") {
      return answer();
    }
    return new Response(readFileSync(path.join(FIXTURES_DIR, `${answer.fixture}.json`), "utf8"), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch: fakeFetch as typeof fetch, requests };
}

/** An error answer in the shape Apify's API documents: a status, and an error's type and message. */
export function apifyError(status: number, type: string, message: string): () => Response {
  return () => new Response(JSON.stringify({ error: { type, message } }), { status });
}

/** One of the Actor's real answers, from tests/fixtures/apify/, as its items. */
export function readActorItems(name: string): Record<string, unknown>[] {
  return JSON.parse(readFileSync(path.join(FIXTURES_DIR, `${name}.json`), "utf8"));
}

/** A fetch that answers every request with Apify MCP's real 401 to a request without a valid token. */
export function createApifyMcp401Fetch(): { fetch: typeof fetch; inits: RequestInit[] } {
  const recorded = JSON.parse(readFileSync(path.join(FIXTURES_DIR, "mcp-401-no-token.json"), "utf8"));
  const inits: RequestInit[] = [];
  const fakeFetch = async (_input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    inits.push(init ?? {});
    return new Response(JSON.stringify(recorded.body), { status: recorded.status, headers: recorded.headers });
  };
  return { fetch: fakeFetch as typeof fetch, inits };
}

/** A tool as Apify's MCP server lists it: its name, and its input schema's properties. */
type ListedTool = { name: string; inputSchema: { type: "object"; properties?: Record<string, unknown> } };

/**
 * The tools Apify's MCP server lists for ?tools=call-actor,gochujang/open-meteo-weather-forecast: call-actor, the
 * Actor's own tool, and the helpers that come with them.
 */
export const APIFY_MCP_TOOLS: ListedTool[] = [
  {
    name: "call-actor",
    inputSchema: {
      type: "object",
      properties: {
        actor: {},
        input: {},
        waitSecs: {},
        callOptions: {
          type: "object",
          properties: { memory: {}, timeout: {}, build: {}, maxItems: {}, maxTotalChargeUsd: {} },
        },
      },
    },
  },
  {
    name: "gochujang--open-meteo-weather-forecast",
    inputSchema: { type: "object", properties: { locations: {}, forecastDays: {}, mode: {}, waitSecs: {} } },
  },
  { name: "get-actor-run", inputSchema: { type: "object", properties: {} } },
  { name: "get-dataset-items", inputSchema: { type: "object", properties: {} } },
  { name: "get-key-value-store-record", inputSchema: { type: "object", properties: {} } },
  { name: "abort-actor-run", inputSchema: { type: "object", properties: {} } },
];

/** A run's answer from Apify's MCP server, with this status: its storages, and its summary and next step. */
export function runAnswer(status = "SUCCEEDED"): CallToolResult {
  const structuredContent = {
    runId: "run-1",
    actorId: "eQZxxMN7oHyh8hFh6",
    status,
    storages: { datasets: { default: { id: "dataset-1", itemCount: 3 } } },
    summary: `${status} in 3s. 3 items; 16 fields available.`,
    nextStep: "Use get-dataset-items with datasetId=dataset-1 and limit (for example 20) to fetch items (3 total).",
  };
  return { content: [{ type: "text", text: JSON.stringify(structuredContent) }], structuredContent };
}

/** A dataset's answer from Apify's MCP server: these items, of this many in all. */
export function itemsAnswer(items: unknown[], totalItemCount = items.length): CallToolResult {
  const structuredContent = {
    datasetId: "dataset-1",
    items,
    itemCount: items.length,
    totalItemCount,
    offset: 0,
    limit: 100,
  };
  return { content: [{ type: "text", text: `${items.length} items.` }], structuredContent };
}

/** An answer of the stand-in to a tools/call: a result, or a function of the call's signal (to fail or hang). */
export type ApifyMcpAnswer = CallToolResult | ((signal?: AbortSignal) => Promise<CallToolResult>);

/** A call that never answers: as the real client does, it fails with the signal's reason when the signal fires. */
export function hangingCall(signal?: AbortSignal): Promise<CallToolResult> {
  return new Promise((_resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason);
      return;
    }
    signal?.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
}

/** A tools/call as the stand-in's client takes it. */
type CallToolArguments = { name: string; arguments?: unknown; options?: { signal?: AbortSignal } };

/**
 * A stand-in for Apify's MCP server, as AI SDK's MCP client sees it: the tools it lists, and its answers to each tool's
 * calls, in order. Every message also goes through the transport's fetch, as the real client's do (initialize, then a
 * session id on each later one), so the lane records them. It counts the connections opened and closed; a close can
 * hang, as AI SDK's would on a session's DELETE that Apify never answers.
 */
export function createApifyMcpStandIn({
  listed = APIFY_MCP_TOOLS,
  answers,
  closeHangs = false,
}: {
  listed?: ListedTool[];
  answers: Record<string, ApifyMcpAnswer[]>;
  closeHangs?: boolean;
}) {
  const calls: { name: string; arguments: unknown }[] = [];
  let connects = 0;
  let closes = 0;
  const createClient = async (config: MCPClientConfig): Promise<McpClient> => {
    connects += 1;
    const transport = config.transport as { url: string; headers?: Record<string, string>; fetch: typeof fetch };
    let id = 0;
    const send = (method: string, params: unknown, signal?: AbortSignal) =>
      transport.fetch(transport.url, {
        method: "POST",
        headers: {
          ...transport.headers,
          "content-type": "application/json",
          accept: "application/json, text/event-stream",
          "mcp-protocol-version": "2025-11-25",
          ...(method === "initialize" ? {} : { "mcp-session-id": "a-session-id-from-apify" }),
        },
        body: JSON.stringify({ method, params, jsonrpc: "2.0", id: id++ }),
        signal,
      });
    await send("initialize", { protocolVersion: "2025-11-25" });
    const client = {
      listTools: async () => {
        await send("tools/list", {});
        return { tools: listed };
      },
      callTool: async ({ name, arguments: args, options }: CallToolArguments) => {
        calls.push({ name, arguments: args });
        await send("tools/call", { name, arguments: args }, options?.signal);
        const answer = answers[name]?.shift();
        if (answer === undefined) {
          throw new Error(`The Apify MCP stand-in has no answer for ${name}`);
        }
        return typeof answer === "function" ? answer(options?.signal) : answer;
      },
      close: async () => {
        closes += 1;
        if (closeHangs) {
          await new Promise(() => undefined);
        }
      },
    };
    return client as unknown as McpClient;
  };
  return { createClient, calls, connects: () => connects, closes: () => closes };
}
