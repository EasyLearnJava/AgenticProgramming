/*
 * tests/stubs/mcp-stand-ins.ts: our MCP server, run in the test's own process: a fetch that hands each request to the
 * /api/mcp handler, whose tools answer from Open-Meteo's recorded answers.
 */
import { createMcpHandler } from "mcp-handler";
import { MCP_SERVER_INFO } from "@/lib/constants";
import { createOpenMeteoClient } from "@/lib/upstream/open-meteo";
import { registerTools } from "@/lib/weather/register-tools";
import { createFakeFetch, createMemoryCache, type FakeAnswer } from "@/tests/stubs/open-meteo-stand-ins";

/** The address the tests give our MCP server; no request ever leaves the process. */
export const TEST_ORIGIN = "https://nimbus.test";

/**
 * A fetch that serves our MCP server in-process, and records every request it was given. Its Open-Meteo calls get the
 * recorded answers given, or go to the fetch given (one that never answers, say).
 */
export function createMcpServerFetch(answers: FakeAnswer[] | typeof fetch): {
  fetch: typeof fetch;
  requests: Request[];
} {
  const openMeteo = createOpenMeteoClient({
    fetch: typeof answers === "function" ? answers : createFakeFetch(answers).fetch,
    cache: createMemoryCache(),
    random: () => 0,
  });
  const handler = createMcpHandler((server) => registerTools(server, { openMeteo }), { serverInfo: MCP_SERVER_INFO });
  const requests: Request[] = [];
  const serverFetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const request = new Request(input, init);
    requests.push(request.clone());
    return handler(request);
  }) as typeof fetch;
  return { fetch: serverFetch, requests };
}
