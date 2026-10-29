/*
 * tests/unit/weather/mcp-request.test.ts: what our public MCP server takes: one JSON-RPC message, of at most 8 KB.
 */
import { describe, expect, it } from "vitest";
import { checkMcpRequest } from "@/lib/weather/mcp-request";

const URL = "https://nimbus.test/api/mcp";
const ONE_MESSAGE = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" });

/** A POST to /api/mcp with this body. */
function post(body: string, headers: Record<string, string> = {}): Request {
  return new Request(URL, { method: "POST", body, headers: { "content-type": "application/json", ...headers } });
}

/** A refusal's status and JSON-RPC error. */
async function refusal(result: Request | Response): Promise<[number, unknown]> {
  expect(result).toBeInstanceOf(Response);
  const response = result as Response;
  return [response.status, ((await response.json()) as { error: unknown }).error];
}

describe("checkMcpRequest", () => {
  it("passes one message on, its body intact, and a GET as it is", async () => {
    const passed = await checkMcpRequest(post(ONE_MESSAGE));
    expect(passed).toBeInstanceOf(Request);
    expect(await (passed as Request).text()).toBe(ONE_MESSAGE);
    const get = new Request(URL);
    expect(await checkMcpRequest(get)).toBe(get);
  });

  it("refuses a batch of messages, which could carry thousands of tool calls", async () => {
    expect(await refusal(await checkMcpRequest(post(`[${ONE_MESSAGE},${ONE_MESSAGE}]`)))).toEqual([
      400,
      { code: -32_600, message: "This server takes one message at a time." },
    ]);
  });

  it("refuses a body over 8 KB, by its declared size or by what arrives", async () => {
    const [declaredStatus] = await refusal(await checkMcpRequest(post(ONE_MESSAGE, { "content-length": "9000" })));
    expect(declaredStatus).toBe(413);
    const big = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: { pad: "x".repeat(9000) } });
    const [actualStatus, error] = await refusal(await checkMcpRequest(post(big)));
    expect([actualStatus, error]).toEqual([413, { code: -32_600, message: "A message can be at most 8192 bytes." }]);
  });

  it("refuses a body that isn't JSON", async () => {
    expect(await refusal(await checkMcpRequest(post("not json")))).toEqual([
      400,
      { code: -32_700, message: "The body isn't JSON." },
    ]);
  });
});
