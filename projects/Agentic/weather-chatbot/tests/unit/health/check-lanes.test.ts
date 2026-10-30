/*
 * tests/unit/health/check-lanes.test.ts: the health check: every check at once, each within its time; a lane works
 * when every check its answers depend on passes, and is off without Apify's token; one health.check line a check, at
 * its class's level when it fails, and one health.done line. Then the four real checks, against stand-ins: Open-Meteo
 * asked itself, our MCP server in-process, and Apify's real 401 at both its doors.
 */
import { describe, expect, it } from "vitest";
import { APIFY_USER_URL, OPEN_METEO_GEOCODING_URL } from "@/lib/constants";
import { AuthError, ContractError, UpstreamUnavailableError } from "@/lib/errors";
import { type Check, type CheckName, checkLanes, createHealthChecks } from "@/lib/health/check-lanes";
import { apifyError, createApifyMcp401Fetch } from "@/tests/stubs/apify-stand-ins";
import { createTestLog } from "@/tests/stubs/log-stand-ins";
import { createMcpServerFetch, TEST_ORIGIN } from "@/tests/stubs/mcp-stand-ins";
import { readFixture } from "@/tests/stubs/open-meteo-stand-ins";

const NOW = new Date("2026-10-30T18:00:00Z");
const TOKEN = "test-token-not-real";
const REQUEST_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";

const passes: Check = async () => undefined;

/** A check that fails with this error. */
const failsWith =
  (error: Error): Check =>
  async () => {
    throw error;
  };

/** The four checks, all passing, but for these. */
function checksWith(overrides: Partial<Record<CheckName, Check>>): Record<CheckName, Check> {
  return { "open-meteo": passes, "our-mcp": passes, "apify-rest": passes, "apify-mcp": passes, ...overrides };
}

/** Each line as its level, event, and check or status. */
const summarize = (lines: Record<string, unknown>[]) =>
  lines.map((line) => `${String(line.level)} ${String(line.event)} ${String(line.check ?? line.status)}`);

describe("checkLanes", () => {
  it("runs every check, says each lane works, and logs one health.check line each, then health.done", async () => {
    const { log, lines } = createTestLog();
    const report = await checkLanes(checksWith({}), { log, clock: () => NOW });
    expect(report).toEqual({
      status: "ok",
      checkedAt: "2026-10-30T18:00:00.000Z",
      checks: {
        "open-meteo": { status: "ok", ms: expect.any(Number) },
        "our-mcp": { status: "ok", ms: expect.any(Number) },
        "apify-rest": { status: "ok", ms: expect.any(Number) },
        "apify-mcp": { status: "ok", ms: expect.any(Number) },
      },
      lanes: { "rest-no-auth": "ok", "mcp-no-auth": "ok", "rest-auth": "ok", "mcp-auth": "ok" },
    });
    expect(summarize(lines)).toEqual([
      "info health.check open-meteo",
      "info health.check our-mcp",
      "info health.check apify-rest",
      "info health.check apify-mcp",
      "info health.done ok",
    ]);
  });

  it("without Apify's token, the auth lanes are off, and the rest can still be all right", async () => {
    const { log, lines } = createTestLog();
    const report = await checkLanes(checksWith({ "apify-rest": undefined, "apify-mcp": undefined }), { log });
    expect(report.status).toBe("ok");
    expect(report.checks["apify-rest"]).toEqual({ status: "off" });
    expect(report.lanes).toEqual({ "rest-no-auth": "ok", "mcp-no-auth": "ok", "rest-auth": "off", "mcp-auth": "off" });
    expect(summarize(lines)).toEqual([
      "info health.check open-meteo",
      "info health.check our-mcp",
      "info health.done ok",
    ]);
  });

  it("a lane is down when a check it needs fails: Open-Meteo takes all four, our MCP server two", async () => {
    const { log } = createTestLog();
    const openMeteoDown = await checkLanes(
      checksWith({ "open-meteo": failsWith(new UpstreamUnavailableError("Open-Meteo answered 503.")) }),
      { log },
    );
    expect(openMeteoDown.status).toBe("down");
    expect(openMeteoDown.checks["open-meteo"]).toEqual({
      status: "down",
      ms: expect.any(Number),
      errorClass: "UpstreamUnavailableError",
    });
    expect(openMeteoDown.lanes).toEqual({
      "rest-no-auth": "down",
      "mcp-no-auth": "down",
      "rest-auth": "down",
      "mcp-auth": "down",
    });
    const ourMcpDown = await checkLanes(checksWith({ "our-mcp": failsWith(new ContractError("No geocode tool.")) }), {
      log,
    });
    expect(ourMcpDown.lanes).toEqual({
      "rest-no-auth": "ok",
      "mcp-no-auth": "down",
      "rest-auth": "ok",
      "mcp-auth": "down",
    });
    const tokenRefused = await checkLanes(checksWith({ "apify-rest": failsWith(new AuthError("401.")) }), { log });
    expect(tokenRefused.lanes).toEqual({
      "rest-no-auth": "ok",
      "mcp-no-auth": "ok",
      "rest-auth": "down",
      "mcp-auth": "ok",
    });
  });

  it("logs a failed check at its class's level: a refused token at error, for Sentry; a timeout at warn", async () => {
    const { log, lines } = createTestLog();
    const never: Check = () => new Promise(() => undefined);
    const report = await checkLanes(
      checksWith({ "apify-rest": failsWith(new AuthError("Apify answered 401.")), "our-mcp": never }),
      { log, timeoutMs: 30 },
    );
    expect(report.checks["our-mcp"]).toEqual({
      status: "down",
      ms: expect.any(Number),
      errorClass: "UpstreamTimeoutError",
    });
    expect(lines).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          level: "error",
          event: "health.check",
          check: "apify-rest",
          errorClass: "AuthError",
        }),
        expect.objectContaining({
          level: "warn",
          event: "health.check",
          check: "our-mcp",
          errorClass: "UpstreamTimeoutError",
          message: "The our-mcp check didn't pass within 30 ms.",
        }),
      ]),
    );
    expect(lines.at(-1)).toMatchObject({ level: "info", event: "health.done", status: "down" });
  });
});

describe("createHealthChecks, against stand-ins", () => {
  it("asks Open-Meteo itself, connects to our MCP server, and meets Apify's real 401 at both its doors", async () => {
    const ourServer = createMcpServerFetch([]);
    const apifyMcp = createApifyMcp401Fetch();
    const openMeteoUrls: string[] = [];
    const sentTo: string[] = [];
    const fetchAll = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      sentTo.push(new URL(url).host);
      if (url.startsWith(TEST_ORIGIN)) {
        return ourServer.fetch(input, init);
      }
      if (url.startsWith("https://mcp.apify.com")) {
        return apifyMcp.fetch(input, init);
      }
      if (url === APIFY_USER_URL) {
        return apifyError(401, "user-or-token-not-found", "User was not found or authentication token is not valid")();
      }
      if (url.startsWith(OPEN_METEO_GEOCODING_URL)) {
        openMeteoUrls.push(url);
        return new Response(readFixture("geocode-paris"), { headers: { "content-type": "application/json" } });
      }
      throw new Error(`No stand-in for ${url}`);
    }) as typeof fetch;
    const { log, lines } = createTestLog();
    const checks = createHealthChecks({
      origin: TEST_ORIGIN,
      requestId: REQUEST_ID,
      apifyToken: TOKEN,
      log,
      fetch: fetchAll,
    });
    const first = await checkLanes(checks, { log });
    expect(first.checks).toEqual({
      "open-meteo": { status: "ok", ms: expect.any(Number) },
      "our-mcp": { status: "ok", ms: expect.any(Number) },
      "apify-rest": { status: "down", ms: expect.any(Number), errorClass: "AuthError" },
      "apify-mcp": { status: "down", ms: expect.any(Number), errorClass: "AuthError" },
    });
    expect(first.lanes).toEqual({ "rest-no-auth": "ok", "mcp-no-auth": "ok", "rest-auth": "down", "mcp-auth": "down" });
    // London, from Open-Meteo itself each time: a second run asks again, since the cache is skipped.
    await checkLanes(checks, { log });
    expect(openMeteoUrls).toHaveLength(2);
    expect(new URL(openMeteoUrls[0] ?? "").searchParams.get("name")).toBe("London");
    expect(new Set(sentTo)).toEqual(
      new Set(["nimbus.test", "mcp.apify.com", "api.apify.com", "geocoding-api.open-meteo.com"]),
    );
    expect(JSON.stringify(lines)).not.toContain(TOKEN);
  });

  it("without Apify's token, never calls Apify; Open-Meteo finding no London fails its check", async () => {
    const ourServer = createMcpServerFetch([]);
    const sentTo: string[] = [];
    const fetchAll = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      sentTo.push(new URL(url).host);
      if (url.startsWith(TEST_ORIGIN)) {
        return ourServer.fetch(input, init);
      }
      // Open-Meteo's answer when it finds nothing: no results at all.
      return new Response('{"generationtime_ms":0.1}', { headers: { "content-type": "application/json" } });
    }) as typeof fetch;
    const { log } = createTestLog();
    const report = await checkLanes(
      createHealthChecks({ origin: TEST_ORIGIN, requestId: REQUEST_ID, log, fetch: fetchAll }),
      {
        log,
      },
    );
    expect(report.checks["open-meteo"]).toEqual({
      status: "down",
      ms: expect.any(Number),
      errorClass: "ContractError",
    });
    expect(report.lanes).toEqual({
      "rest-no-auth": "down",
      "mcp-no-auth": "down",
      "rest-auth": "off",
      "mcp-auth": "off",
    });
    expect(new Set(sentTo)).toEqual(new Set(["nimbus.test", "geocoding-api.open-meteo.com"]));
  });
});
