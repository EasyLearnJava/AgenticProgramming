/*
 * app/api/mcp/route.ts: our MCP server, the door of MCP · no auth: the four weather tools over Streamable HTTP, at
 * /api/mcp, which the chat route calls. Public on purpose: any MCP client can try it, and the same URL works in
 * Claude or Cursor; so each request is checked first, one message at a time.
 */
import { waitUntil } from "@vercel/functions";
import { createMcpHandler } from "mcp-handler";
import { MCP_SERVER_INFO, REQUEST_ID_HEADER, VERCEL_ID_HEADER } from "@/lib/constants";
import { flushLogs } from "@/lib/logger";
import { markTrace } from "@/lib/sentry";
import { toRequestId } from "@/lib/utils";
import { checkMcpRequest } from "@/lib/weather/mcp-request";
import { registerTools } from "@/lib/weather/register-tools";

// A tool call's own budget is 8 s; the function stops at 60 s, as the chat route does.
export const maxDuration = 60;

const handler = createMcpHandler((server) => registerTools(server), { serverInfo: MCP_SERVER_INFO });

/**
 * Answers MCP requests (POST; GET answers 405, since the server keeps no sessions); a batch or a large body is refused.
 * Once it has answered, its lines go out.
 */
async function serveMcp(request: Request): Promise<Response> {
  // Its trace, which the chat's continues when the MCP lane sent it, carries the chat's request id (step 9).
  markTrace(toRequestId(request.headers.get(REQUEST_ID_HEADER), request.headers.get(VERCEL_ID_HEADER)));
  try {
    // ① Check the request: one JSON-RPC message, at most 8 KB.
    const checked = await checkMcpRequest(request);
    // ② Hand it to the MCP server, which runs the tool.
    return checked instanceof Response ? checked : await handler(checked);
  } finally {
    // ③ Its lines go to Axiom, and its errors to Sentry (step 9). The tool's own line is in: the server answers with
    // plain JSON, once the tool has run, since our tools send nothing before their result.
    waitUntil(flushLogs());
  }
}

export { serveMcp as GET, serveMcp as POST };
