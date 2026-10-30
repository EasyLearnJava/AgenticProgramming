/*
 * lib/upstream/apify-mcp.ts: the Apify Actor behind the auth lanes, run through Apify's MCP server (mcp.apify.com) with
 * our token, for MCP · with auth. Apify's call-actor runs it with the REST door's build, time and cost limits, in its
 * callOptions (the Actor's own tool takes none of them), and answers with the run's status and storage ids, not its
 * items (Apify's RunResponse holds none); so a run is two tools/call messages: call-actor, then get-dataset-items. The
 * Actor's own tool is listed too, only so our pin can check its input: call-actor checks ours against the same schema,
 * the default build's, before it runs the pinned one. The connection opens on the first run, so a question that needs
 * no forecast never pays for the handshake, and its tool list is checked then, once: our pin (PLAN.md 7.4). Nothing is
 * retried, since a run costs money, and the lane falls back instead; closing waits at most 1 s for Apify. Each message
 * writes one upstream.mcp line; every request the page sees has the token and the session's id masked. The health
 * check connects and checks the pin too, and closes, running nothing.
 */
import "server-only";
import { createMCPClient, type MCPClientConfig } from "@ai-sdk/mcp";
import { z } from "zod";
import {
  ACTOR_TOOL_NAME,
  APIFY_ACTOR,
  APIFY_ACTOR_BUILD,
  APIFY_DATASET_TOOL,
  APIFY_MAX_CHARGE_USD,
  APIFY_MCP_CLOSE_TIMEOUT_MS,
  APIFY_MCP_CONNECT_TIMEOUT_MS,
  APIFY_MCP_URL,
  APIFY_RUN_TIMEOUT_SECONDS,
  APIFY_RUN_TOOL,
  MAX_ACTOR_ITEMS,
} from "@/lib/constants";
import {
  AppError,
  AuthError,
  BudgetExceededError,
  ContractError,
  UpstreamRateLimitedError,
  UpstreamTimeoutError,
  UpstreamUnavailableError,
} from "@/lib/errors";
import { type Logger, logger } from "@/lib/logger";
import type { McpClient, WireRequest } from "@/lib/types";
import type { ActorRunInput, ApifyCallOptions, ApifyClient } from "@/lib/upstream/apify";
import {
  findToolsCall,
  timeoutSignal,
  toAbortKind,
  toFieldNames,
  toHost,
  toResultText,
  toStatusCode,
  toWireRequest,
  waitAtMost,
} from "@/lib/utils";

/** The Actor through Apify's MCP server: the REST client's one call, and closing the connection a run opened. */
export type ApifyMcpClient = ApifyClient & { close: () => Promise<void> };

type ApifyMcpOptions = {
  token: string;
  fetch?: typeof fetch;
  createClient?: (config: MCPClientConfig) => Promise<McpClient>;
  now?: () => Date;
  connectTimeoutMs?: number;
  closeTimeoutMs?: number;
};

/** An open connection to Apify's MCP server: the client, and every request it has sent, as the wire view shows it. */
type ApifyConnection = { client: McpClient; sent: readonly WireRequest[] };

/** What a connect or a call takes besides its own arguments: the run's signal, the request's logger, the clock. */
type CallContext = { signal: AbortSignal | undefined; log: Logger; now: () => Date };

const HOST = toHost(APIFY_MCP_URL);
// What the page sees instead of the token and the session's id.
const MASKS: Readonly<Record<string, string>> = {
  authorization: "Bearer <APIFY_TOKEN>",
  "mcp-session-id": "<session id>",
};
// Our pin: the fields call-actor must take, the run's three limits inside its callOptions among them, since Apify's
// server drops a key it doesn't know without a word; and the Actor's three, which its own tool must take.
const RUN_FIELDS = [
  "actor",
  "input",
  "waitSecs",
  "callOptions.build",
  "callOptions.timeout",
  "callOptions.maxTotalChargeUsd",
];
const ACTOR_FIELDS = ["locations", "forecastDays", "mode"];
const HTTP_UNAUTHORIZED = 401;
const HTTP_PAYMENT_REQUIRED = 402;
const HTTP_FORBIDDEN = 403;
const HTTP_TOO_MANY_REQUESTS = 429;
const HTTP_SERVER_ERROR = 500;
// Apify's statuses for a run that hasn't ended, or ran out of time; any other but SUCCEEDED means it failed.
const STILL_RUNNING = ["READY", "RUNNING", "TIMING-OUT", "TIMED-OUT"];
const MAX_STATUS_CHARS = 40;
// An error result's words that say the account can't pay for the run: our reading, since Apify's MCP server doesn't
// document them; any other error result is a ContractError.
const PAYMENT_WORDS = /payment|credit|usage limit|not enough usage/i;

// The run's answer: its status, and its default dataset's id.
const RunAnswerSchema = z.object({
  status: z.string(),
  storages: z.object({ datasets: z.object({ default: z.object({ id: z.string() }) }) }),
});
// The dataset's answer: its items, and how many it holds in all.
const ItemsAnswerSchema = z.object({ items: z.array(z.unknown()), totalItemCount: z.number().optional() });

/**
 * call-actor's arguments for a run of the Actor: the Actor, its input, how long Apify's server waits for the run, and
 * the REST door's limits, from the same constants: the pinned build, 18 s and $0.01.
 */
export function toMcpRunArguments(input: ActorRunInput): Record<string, unknown> {
  return {
    actor: APIFY_ACTOR,
    input,
    waitSecs: APIFY_RUN_TIMEOUT_SECONDS,
    callOptions: {
      build: APIFY_ACTOR_BUILD,
      timeout: APIFY_RUN_TIMEOUT_SECONDS,
      maxTotalChargeUsd: APIFY_MAX_CHARGE_USD,
    },
  };
}

/**
 * A failed connect or call, as one of our classes. The signal comes first, whatever was going on: a stop (passed on as
 * it is), or past the budget. Then ours, as they are; then Apify's HTTP status; anything else is no answer.
 */
function toApifyError(error: unknown, signal: AbortSignal | undefined, what: string): unknown {
  const abortKind = toAbortKind(signal);
  if (abortKind === "stop") {
    return signal?.reason;
  }
  if (abortKind === "timeout") {
    return new UpstreamTimeoutError(`Apify's MCP server didn't answer the ${what} in time.`, { cause: error });
  }
  if (error instanceof AppError) {
    return error;
  }
  const status = toStatusCode(error);
  if (status === HTTP_UNAUTHORIZED || status === HTTP_FORBIDDEN) {
    return new AuthError(`Apify's MCP server answered the ${what} with ${status}.`);
  }
  if (status === HTTP_PAYMENT_REQUIRED) {
    return new BudgetExceededError(`Apify's MCP server answered the ${what} with 402.`);
  }
  if (status === HTTP_TOO_MANY_REQUESTS) {
    return new UpstreamRateLimitedError(`Apify's MCP server answered the ${what} with 429.`, undefined);
  }
  if (status !== undefined && status >= HTTP_SERVER_ERROR) {
    return new UpstreamUnavailableError(`Apify's MCP server answered the ${what} with ${status}.`);
  }
  return status === undefined
    ? new UpstreamUnavailableError("Apify's MCP server can't be reached.", { cause: error })
    : new ContractError(`Apify's MCP server refused the ${what} with ${status}.`);
}

/** The fields, as paths into nested objects ("callOptions.build"), that a listed tool's input schema doesn't take. */
function toMissingFields(tool: { inputSchema?: unknown }, fields: readonly string[]): string[] {
  return fields.filter((field) => {
    let schema: unknown = tool.inputSchema;
    for (const name of field.split(".")) {
      const { properties = {} } = (schema ?? {}) as { properties?: Record<string, unknown> };
      if (!Object.hasOwn(properties, name)) {
        return true;
      }
      schema = properties[name];
    }
    return false;
  });
}

/**
 * Our pin (PLAN.md 7.4): the server lists call-actor, taking the Actor, its input, the wait and the run's three limits;
 * the Actor's own tool, taking the Actor's three fields; and get-dataset-items.
 */
function checkTools(tools: readonly { name: string; inputSchema?: unknown }[]): void {
  const runTool = tools.find((tool) => tool.name === APIFY_RUN_TOOL);
  const actorTool = tools.find((tool) => tool.name === ACTOR_TOOL_NAME);
  if (runTool === undefined || actorTool === undefined || !tools.some((tool) => tool.name === APIFY_DATASET_TOOL)) {
    throw new ContractError(
      `Apify's MCP server doesn't list ${APIFY_RUN_TOOL}, ${ACTOR_TOOL_NAME} and ${APIFY_DATASET_TOOL}.`,
    );
  }
  for (const [tool, name, fields] of [
    [runTool, APIFY_RUN_TOOL, RUN_FIELDS],
    [actorTool, ACTOR_TOOL_NAME, ACTOR_FIELDS],
  ] as const) {
    const missing = toMissingFields(tool, fields);
    if (missing.length > 0) {
      throw new ContractError(`Apify's ${name} tool doesn't take ${missing.join(", ")}.`);
    }
  }
}

/**
 * Connects to Apify's MCP server with our token, within its own time, and checks its tools; one lane.connect line,
 * either way. A 2025 server, with sessions (its 401 exposes Mcp-Session-Id), so no 2026 discovery first; and no
 * retries, since a retried run would be a second, paid one. A connection that fails its check is closed, within its
 * own time too.
 */
async function connect(
  {
    token,
    fetchApify,
    createClient,
    connectTimeoutMs,
    closeTimeoutMs,
  }: Required<Pick<ApifyMcpOptions, "token">> & {
    fetchApify: typeof fetch;
    createClient: (config: MCPClientConfig) => Promise<McpClient>;
    connectTimeoutMs: number;
    closeTimeoutMs: number;
  },
  { signal, log, now }: CallContext,
): Promise<ApifyConnection> {
  const startedAt = now().getTime();
  const logConnect = (fields: Record<string, unknown>) =>
    log.info({ event: "lane.connect", host: HOST, ms: now().getTime() - startedAt, ...fields });
  const sent: WireRequest[] = [];
  const recordingFetch = ((input: string | URL | Request, init?: RequestInit) => {
    sent.push(toWireRequest(input, init, MASKS));
    return fetchApify(input, init);
  }) as typeof fetch;
  const connectSignal = timeoutSignal(connectTimeoutMs, signal);
  let client: McpClient | undefined;
  try {
    client = await createClient({
      transport: {
        type: "http",
        url: APIFY_MCP_URL,
        headers: { authorization: `Bearer ${token}` },
        fetch: recordingFetch,
      },
      initializationOptions: { signal: connectSignal },
      protocolVersionDiscovery: false,
      maxRetries: 0,
    });
    const { tools } = await client.listTools({ options: { signal: connectSignal } });
    checkTools(tools);
    logConnect({ status: "ok", tools: tools.length });
    return { client, sent };
  } catch (error) {
    if (client !== undefined) {
      await waitAtMost(client.close(), closeTimeoutMs);
    }
    const failure = toApifyError(error, connectSignal, "connection");
    if (toAbortKind(signal) !== "stop") {
      const errorClass = failure instanceof Error ? failure.name : "unknown";
      logConnect({ status: "failed", errorClass, httpStatus: toStatusCode(error) });
    }
    throw failure;
  }
}

/**
 * An error result, as one of our classes: the account can't pay (by its words), or a refusal. Its text isn't kept: it
 * can quote the input.
 */
function toResultError(tool: string, text: string): AppError {
  return PAYMENT_WORDS.test(text)
    ? new BudgetExceededError(`Apify's MCP server said ${tool} can't be paid for.`)
    : new ContractError(`Apify's MCP server answered ${tool} with an error.`);
}

/** One tools/call to Apify's MCP server: its structured content, or one of our classes; one upstream.mcp line. */
async function callTool(
  { client }: ApifyConnection,
  tool: string,
  args: Record<string, unknown>,
  { signal, log, now }: CallContext,
): Promise<unknown> {
  const startedAt = now().getTime();
  const logCall = (fields: Record<string, unknown>) =>
    log.info({
      event: "upstream.mcp",
      upstream: "apify",
      host: HOST,
      tool,
      ms: now().getTime() - startedAt,
      ...fields,
    });
  try {
    const result = await client.callTool({ name: tool, arguments: args, options: { signal } });
    if (result.isError === true) {
      throw toResultError(tool, toResultText(result));
    }
    logCall({ status: "ok" });
    return result.structuredContent;
  } catch (error) {
    const failure = toApifyError(error, signal, tool);
    if (toAbortKind(signal) !== "stop") {
      const errorClass = failure instanceof Error ? failure.name : "unknown";
      logCall({ status: "failed", errorClass, httpStatus: toStatusCode(error) });
    }
    throw failure;
  }
}

/** The run's dataset id, from the run's answer; a run that didn't succeed is a timeout or a failure, by its status. */
function toDatasetId(answer: unknown): string {
  const parsed = RunAnswerSchema.safeParse(answer);
  if (!parsed.success) {
    throw new ContractError(`Apify's run answer isn't the shape we read: ${toFieldNames(parsed.error.issues)}.`);
  }
  const { status, storages } = parsed.data;
  const shownStatus = status.slice(0, MAX_STATUS_CHARS);
  if (STILL_RUNNING.includes(status)) {
    throw new UpstreamTimeoutError(`The Actor's run was ${shownStatus} after ${APIFY_RUN_TIMEOUT_SECONDS} s.`);
  }
  if (status !== "SUCCEEDED") {
    throw new UpstreamUnavailableError(`The Actor's run ended as ${shownStatus}.`);
  }
  return storages.datasets.default.id;
}

/** The run's items, from the dataset's answer: all of them, in one read, or a ContractError. */
function toItems(answer: unknown): unknown[] {
  const parsed = ItemsAnswerSchema.safeParse(answer);
  if (!parsed.success) {
    throw new ContractError(`Apify's dataset answer isn't the shape we read: ${toFieldNames(parsed.error.issues)}.`);
  }
  const { items, totalItemCount } = parsed.data;
  if (totalItemCount !== undefined && totalItemCount > items.length) {
    throw new ContractError(`Apify's dataset holds ${totalItemCount} items, more than one read.`);
  }
  return items;
}

/** Makes a client for the Actor through Apify's MCP server, with our token; it connects on its first run. */
export function createApifyMcpClient({
  token,
  fetch: fetchApify = fetch,
  createClient = createMCPClient,
  now = () => new Date(),
  connectTimeoutMs = APIFY_MCP_CONNECT_TIMEOUT_MS,
  closeTimeoutMs = APIFY_MCP_CLOSE_TIMEOUT_MS,
}: ApifyMcpOptions): ApifyMcpClient {
  let connecting: Promise<ApifyConnection> | undefined;
  let closing: Promise<void> | undefined;
  return {
    async runActor(input, { signal, log = logger } = {}) {
      const context: CallContext = { signal, log, now };
      // The connection, opened by the first run and kept, or its failure, which each later run meets too.
      connecting ??= connect({ token, fetchApify, createClient, connectTimeoutMs, closeTimeoutMs }, context);
      const connection = await connecting;
      // ① The run: call-actor, with the pinned build, 18 s and $0.01; its server waits up to 18 s for the run, then
      // answers with its dataset's id.
      const args = toMcpRunArguments(input);
      const datasetId = toDatasetId(await callTool(connection, APIFY_RUN_TOOL, args, context));
      // ② The items: Apify's get-dataset-items, all of them in one read.
      const read = await callTool(connection, APIFY_DATASET_TOOL, { datasetId, limit: MAX_ACTOR_ITEMS }, context);
      const items = toItems(read);
      // The request the chip shows: the run's, as it was sent, with the token and the session's id masked.
      const request = findToolsCall(connection.sent, APIFY_RUN_TOOL, args);
      if (request === undefined) {
        throw new ContractError("The run's tools/call request wasn't recorded.");
      }
      return { items, request, fetchedAt: now().toISOString() };
    },
    // AI SDK ends Apify's session with a DELETE that has no time limit of its own; the answer's end waits for this.
    // Only the first close of an open connection runs: a lane is closed twice when an answer fails (the error, then
    // the end), and a second DELETE would wait its own second. A close with nothing open isn't kept, so a connection
    // that a run opens after it is still closed.
    async close() {
      const connection = await connecting?.catch(() => undefined);
      if (connection !== undefined) {
        closing ??= waitAtMost(connection.client.close(), closeTimeoutMs);
        await closing;
      }
    },
  };
}

/**
 * Checks Apify's MCP server, running nothing (the health check, step 9): connects with our token, checks its tool list
 * against our pin, and closes, each within its own time; one lane.connect line, either way.
 */
export async function checkApifyMcp({
  token,
  fetch: fetchApify = fetch,
  createClient = createMCPClient,
  now = () => new Date(),
  connectTimeoutMs = APIFY_MCP_CONNECT_TIMEOUT_MS,
  closeTimeoutMs = APIFY_MCP_CLOSE_TIMEOUT_MS,
  signal,
  log = logger,
}: ApifyMcpOptions & ApifyCallOptions): Promise<void> {
  const settings = { token, fetchApify, createClient, connectTimeoutMs, closeTimeoutMs };
  const connection = await connect(settings, { signal, log, now });
  await waitAtMost(connection.client.close(), closeTimeoutMs);
}
