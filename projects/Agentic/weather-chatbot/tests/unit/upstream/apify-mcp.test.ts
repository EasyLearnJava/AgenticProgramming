/*
 * tests/unit/upstream/apify-mcp.test.ts: the Actor through Apify's MCP server: one connection, opened by the first run
 * and checked against our pin; a run as two tools/call messages (call-actor, then get-dataset-items); the request
 * recorded with the token and the session's id masked; every failure as one of our classes, Apify MCP's real 401
 * through AI SDK's own client included; and the log lines, which never hold the token.
 */
import { describe, expect, it } from "vitest";
import {
  AuthError,
  BudgetExceededError,
  ContractError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import type { ActorRunInput } from "@/lib/upstream/apify";
import { createApifyMcpClient } from "@/lib/upstream/apify-mcp";
import {
  APIFY_MCP_TOOLS,
  type ApifyMcpAnswer,
  createApifyMcp401Fetch,
  createApifyMcpStandIn,
  hangingCall,
  itemsAnswer,
  readActorItems,
  runAnswer,
} from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";

const TOKEN = "test-token-not-real";
const NOW = new Date("2026-10-29T16:00:00Z");
const DALLAS: ActorRunInput = {
  locations: [{ name: "Dallas", latitude: 32.78, longitude: -96.81 }],
  forecastDays: 3,
  mode: "daily",
};
const DAILY = readActorItems("actor-dallas-daily");
const ACTOR_TOOL = "gochujang--open-meteo-weather-forecast";

/** A client whose Apify MCP server is the stand-in, answering each tool's calls in order. */
function clientWith(answers: Record<string, ApifyMcpAnswer[]>, listed = APIFY_MCP_TOOLS) {
  const server = createApifyMcpStandIn({ answers, listed });
  const client = createApifyMcpClient({
    token: TOKEN,
    fetch: (async () => new Response("{}")) as typeof fetch,
    createClient: server.createClient,
    now: () => NOW,
  });
  const { log, lines } = createTestLog();
  return { client, server, log, lines };
}

// call-actor's arguments for the Dallas run: the Actor, its input, the wait, and the REST door's limits.
const RUN_ARGUMENTS = {
  actor: "gochujang/open-meteo-weather-forecast",
  input: DALLAS,
  waitSecs: 18,
  callOptions: { build: "1.0.9", timeout: 18, maxTotalChargeUsd: 0.01 },
};

/** One run's answers: the run, then its items; fresh each time, since the stand-in uses them up. */
const oneRun = () => ({ "call-actor": [runAnswer()], "get-dataset-items": [itemsAnswer(DAILY)] });

describe("a run through Apify's MCP server", () => {
  it("runs the Actor through call-actor, with the REST door's limits, then reads all its items", async () => {
    const { client, server, log, lines } = clientWith(oneRun());
    const run = await client.runActor(DALLAS, { log });
    expect(server.calls).toEqual([
      { name: "call-actor", arguments: RUN_ARGUMENTS },
      { name: "get-dataset-items", arguments: { datasetId: "dataset-1", limit: 100 } },
    ]);
    expect(run.items).toEqual(DAILY);
    expect(run.fetchedAt).toBe(NOW.toISOString());
    expect(lines).toEqual([
      expect.objectContaining({ event: "lane.connect", host: "mcp.apify.com", status: "ok", tools: 6 }),
      expect.objectContaining({ event: "upstream.mcp", upstream: "apify", tool: "call-actor", status: "ok" }),
      expect.objectContaining({ event: "upstream.mcp", tool: "get-dataset-items", status: "ok" }),
    ]);
  });

  it("records the run's request as it was sent, with the token and the session's id masked", async () => {
    const { client, log, lines } = clientWith(oneRun());
    const run = await client.runActor(DALLAS, { log });
    expect(run.request).toMatchObject({
      method: "POST",
      url: "https://mcp.apify.com/?tools=call-actor,gochujang/open-meteo-weather-forecast",
      headers: { authorization: "Bearer <APIFY_TOKEN>", "mcp-session-id": "<session id>" },
    });
    expect(JSON.parse(run.request.body ?? "{}")).toMatchObject({
      method: "tools/call",
      params: { name: "call-actor", arguments: RUN_ARGUMENTS },
    });
    expect(JSON.stringify([run.request, lines])).not.toContain(TOKEN);
  });

  it("connects once: a second run uses the same connection", async () => {
    const { client, server, log } = clientWith({
      "call-actor": [runAnswer(), runAnswer()],
      "get-dataset-items": [itemsAnswer(DAILY), itemsAnswer(DAILY)],
    });
    await client.runActor(DALLAS, { log });
    await client.runActor(DALLAS, { log });
    expect(server.connects()).toBe(1);
  });
});

describe("a failed run", () => {
  it("Apify MCP's real 401, through AI SDK's client: AuthError; a later run meets it, not reconnecting", async () => {
    const apify = createApifyMcp401Fetch();
    const client = createApifyMcpClient({ token: TOKEN, fetch: apify.fetch, now: () => NOW });
    const { log, lines } = createTestLog();
    await expect(client.runActor(DALLAS, { log })).rejects.toBeInstanceOf(AuthError);
    const requests = apify.inits.length;
    await expect(client.runActor(DALLAS, { log })).rejects.toBeInstanceOf(AuthError);
    expect(apify.inits.length).toBe(requests);
    // The token went in the request's header, and nowhere else.
    expect(new Headers(apify.inits[0]?.headers).get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(lines).toEqual([
      expect.objectContaining({ event: "lane.connect", status: "failed", errorClass: "AuthError", httpStatus: 401 }),
    ]);
    expect(JSON.stringify(lines)).not.toContain(TOKEN);
  });

  it("a server without our tools, or whose tools lack their fields: ContractError, our pin", async () => {
    const withoutDataset = APIFY_MCP_TOOLS.filter((tool) => tool.name !== "get-dataset-items");
    const narrowed = (name: string, properties: Record<string, unknown>) =>
      APIFY_MCP_TOOLS.map((tool) =>
        tool.name === name ? { ...tool, inputSchema: { type: "object" as const, properties } } : tool,
      );
    for (const [listed, message] of [
      [withoutDataset, `Apify's MCP server doesn't list call-actor, ${ACTOR_TOOL} and get-dataset-items.`],
      [
        // Apify renamed a limit: its server would drop ours without a word.
        narrowed("call-actor", {
          actor: {},
          input: {},
          waitSecs: {},
          callOptions: { type: "object", properties: { timeout: {}, maxTotalChargeUsd: {} } },
        }),
        "Apify's call-actor tool doesn't take callOptions.build.",
      ],
      [narrowed(ACTOR_TOOL, { mode: {} }), `Apify's ${ACTOR_TOOL} tool doesn't take locations, forecastDays.`],
    ] as const) {
      const { client, log } = clientWith(oneRun(), [...listed]);
      const error = await client.runActor(DALLAS, { log }).catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(ContractError);
      expect((error as Error).message).toBe(message);
    }
  });

  it("a run going after 18 s: a timeout; failed: unavailable; another shape: ContractError, by field", async () => {
    const cases: [ApifyMcpAnswer, new (...args: never[]) => Error, string][] = [
      [runAnswer("RUNNING"), UpstreamTimeoutError, "The Actor's run was RUNNING after 18 s."],
      [runAnswer("FAILED"), UpstreamUnavailableError, "The Actor's run ended as FAILED."],
      [
        { content: [], structuredContent: { status: "SUCCEEDED" } },
        ContractError,
        "Apify's run answer isn't the shape we read: storages.",
      ],
    ];
    for (const [answer, errorClass, message] of cases) {
      const { client, log } = clientWith({ "call-actor": [answer] });
      const error = await client.runActor(DALLAS, { log }).catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(errorClass);
      expect((error as Error).message).toBe(message);
    }
  });

  it("an error result: BudgetExceededError when it says it can't pay, else ContractError; text unkept", async () => {
    const errorResult = (text: string) => ({ content: [{ type: "text" as const, text }], isError: true });
    for (const [text, errorClass] of [
      ["You have exceeded your usage limit for this month.", BudgetExceededError],
      ["Input is not valid: Dallas, 32.78", ContractError],
    ] as const) {
      const { client, log, lines } = clientWith({ "call-actor": [errorResult(text)] });
      const error = await client.runActor(DALLAS, { log }).catch((caught: unknown) => caught);
      expect(error).toBeInstanceOf(errorClass);
      expect(JSON.stringify([(error as Error).message, lines])).not.toContain("Dallas");
    }
  });

  it("a dataset holding more items than one read: ContractError", async () => {
    const { client, log } = clientWith({ "call-actor": [runAnswer()], "get-dataset-items": [itemsAnswer(DAILY, 300)] });
    const error = await client.runActor(DALLAS, { log }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as Error).message).toBe("Apify's dataset holds 300 items, more than one read.");
  });

  it("past the run's budget: a timeout; a stop: passed on as it is, and not logged", async () => {
    const slow = clientWith({ "call-actor": [hangingCall] });
    await expect(
      slow.client.runActor(DALLAS, { log: slow.log, signal: AbortSignal.timeout(20) }),
    ).rejects.toBeInstanceOf(UpstreamTimeoutError);
    const stopped = clientWith({ "call-actor": [hangingCall] });
    const controller = new AbortController();
    const pending = stopped.client.runActor(DALLAS, { log: stopped.log, signal: controller.signal });
    setTimeout(() => controller.abort(Object.assign(new Error("Closed."), { name: "ResponseAborted" })), 10);
    await expect(pending).rejects.toMatchObject({ name: "ResponseAborted" });
    expect(stopped.lines.filter((line) => line.event === "upstream.mcp")).toEqual([]);
  });
});

describe("closing", () => {
  it("closes a run's connection once, though closed twice (an error, then the end); none if none", async () => {
    const used = clientWith(oneRun());
    await used.client.runActor(DALLAS, { log: used.log });
    await used.client.close();
    await used.client.close();
    expect(used.server.closes()).toBe(1);
    const unused = clientWith(oneRun());
    await unused.client.close();
    expect([unused.server.connects(), unused.server.closes()]).toEqual([0, 0]);
  });

  it("still closes a connection that a run opens after an early close, as after an error part mid-answer", async () => {
    const early = clientWith(oneRun());
    await early.client.close();
    await early.client.runActor(DALLAS, { log: early.log });
    await early.client.close();
    expect([early.server.connects(), early.server.closes()]).toEqual([1, 1]);
  });

  it("waits at most its time for Apify to close, after a run or a failed pin: a DELETE never answered", async () => {
    const hangingClose = (listed = APIFY_MCP_TOOLS) => {
      const server = createApifyMcpStandIn({ answers: oneRun(), listed, closeHangs: true });
      const client = createApifyMcpClient({
        token: TOKEN,
        fetch: (async () => new Response("{}")) as typeof fetch,
        createClient: server.createClient,
        now: () => NOW,
        closeTimeoutMs: 20,
      });
      return { server, client };
    };
    const { log } = createTestLog();
    const afterRun = hangingClose();
    await afterRun.client.runActor(DALLAS, { log });
    await afterRun.client.close();
    expect(afterRun.server.closes()).toBe(1);
    const afterPin = hangingClose([]);
    await expect(afterPin.client.runActor(DALLAS, { log })).rejects.toBeInstanceOf(ContractError);
    expect(afterPin.server.closes()).toBe(1);
  });
});
