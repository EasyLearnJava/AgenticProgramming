/*
 * lib/weather/mcp-request.ts: what our public MCP server accepts before any tool runs: one JSON-RPC message at a time
 * (a batch could carry up to 100 tool calls in one request, past any per-request rate limit), of at most 8 KB.
 */
import "server-only";
import { MAX_MCP_BODY_BYTES } from "@/lib/constants";

const HTTP_BAD_REQUEST = 400;
const HTTP_PAYLOAD_TOO_LARGE = 413;
const JSON_RPC_PARSE_ERROR = -32_700;
const JSON_RPC_INVALID_REQUEST = -32_600;

/** A refusal, as a JSON-RPC error that any MCP client can read, with its HTTP status. */
function toRefusal(status: number, code: number, message: string): Response {
  return Response.json({ jsonrpc: "2.0", id: null, error: { code, message } }, { status });
}

/** Checks a request to /api/mcp: the request to hand to the MCP server, or the response that refuses it. */
export async function checkMcpRequest(request: Request): Promise<Request | Response> {
  // ① Only a POST carries a message; the server answers anything else itself (a GET gets 405).
  if (request.method !== "POST") {
    return request;
  }
  // ② The body's size, as declared, then as read.
  const tooLarge = `A message can be at most ${MAX_MCP_BODY_BYTES} bytes.`;
  if (Number(request.headers.get("content-length") ?? "0") > MAX_MCP_BODY_BYTES) {
    return toRefusal(HTTP_PAYLOAD_TOO_LARGE, JSON_RPC_INVALID_REQUEST, tooLarge);
  }
  const body = await request.text();
  if (new TextEncoder().encode(body).length > MAX_MCP_BODY_BYTES) {
    return toRefusal(HTTP_PAYLOAD_TOO_LARGE, JSON_RPC_INVALID_REQUEST, tooLarge);
  }
  // ③ One JSON-RPC message, not a batch.
  let message: unknown;
  try {
    message = JSON.parse(body);
  } catch {
    return toRefusal(HTTP_BAD_REQUEST, JSON_RPC_PARSE_ERROR, "The body isn't JSON.");
  }
  if (Array.isArray(message)) {
    return toRefusal(HTTP_BAD_REQUEST, JSON_RPC_INVALID_REQUEST, "This server takes one message at a time.");
  }
  // ④ The same request, its body already read, for the MCP server.
  return new Request(request.url, { method: "POST", headers: request.headers, body, signal: request.signal });
}
