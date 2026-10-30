/*
 * tests/unit/app/api/health/route.test.ts: GET /api/health: what works, per lane, as JSON: 200 when every lane that's
 * on works, kept a minute at the CDN; 503 when one doesn't, never kept; one run answers every request to this copy of
 * the function for a minute; its lines go out once the run is done. The checks are stand-ins, so nothing leaves the
 * machine.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LogLine } from "@/tests/stubs/log-stand-ins";

// The app's logger, swapped for one whose lines the tests can read; and flushLogs, for one that notes how many lines
// had been written when it was called.
const { lines, flushedAt } = vi.hoisted(() => ({ lines: [] as LogLine[], flushedAt: [] as number[] }));
vi.mock("@/lib/logger", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/logger")>();
  const write = (line: string) => {
    lines.push(JSON.parse(line) as LogLine);
  };
  return {
    ...actual,
    logger: actual.createLogger({ level: "info", destination: { write } }),
    flushLogs: async () => {
      flushedAt.push(lines.length);
    },
  };
});

// Vercel's waitUntil, swapped for one that keeps what it's given: what the route keeps the function alive for.
const { kept } = vi.hoisted(() => ({ kept: [] as Promise<unknown>[] }));
vi.mock("@vercel/functions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vercel/functions")>();
  return {
    ...actual,
    waitUntil: (promise: Promise<unknown>) => {
      kept.push(promise);
    },
  };
});

// The checks, swapped for stand-ins: each run is counted, and our MCP server's check fails when a test says so. Its
// failure is a plain Error, which the check reports as UnexpectedError: each test loads the route afresh, so an error
// class from this file wouldn't be the route's own (the classes' own mapping is check-lanes.test.ts's). No Apify token
// here, so the auth lanes are off.
const { scenario } = vi.hoisted(() => ({ scenario: { runs: 0, isOurMcpDown: false } }));
vi.mock("@/lib/health/check-lanes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/health/check-lanes")>();
  return {
    ...actual,
    createHealthChecks: () => {
      scenario.runs += 1;
      return {
        "open-meteo": async () => undefined,
        "our-mcp": async () => {
          if (scenario.isOurMcpDown) {
            throw new Error("Our MCP server is down.");
          }
        },
        "apify-rest": undefined,
        "apify-mcp": undefined,
      };
    },
  };
});

type Get = (request: Request) => Promise<Response>;
let get: Get;
let now = 0;

beforeEach(async () => {
  lines.length = 0;
  flushedAt.length = 0;
  kept.length = 0;
  scenario.runs = 0;
  scenario.isOurMcpDown = false;
  now = Date.parse("2026-10-30T18:00:00Z");
  vi.spyOn(Date, "now").mockImplementation(() => now);
  // The route keeps its latest run between requests, so each test starts from a fresh copy of it.
  vi.resetModules();
  get = (await import("@/app/api/health/route")).GET;
});

const healthGet = () => new Request("https://nimbus.test/api/health");

describe("GET /api/health", () => {
  it("answers what works, per lane: 200 when every lane that's on works, kept a minute at the CDN", async () => {
    const response = await get(healthGet());
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("public, max-age=0, s-maxage=60");
    const report = await response.json();
    expect(report).toMatchObject({
      status: "ok",
      lanes: { "rest-no-auth": "ok", "mcp-no-auth": "ok", "rest-auth": "off", "mcp-auth": "off" },
    });
  });

  it("answers 503 when a lane is down, with the failing check's class; a 503 is never kept", async () => {
    scenario.isOurMcpDown = true;
    const response = await get(healthGet());
    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const report = await response.json();
    expect(report.checks["our-mcp"]).toMatchObject({ status: "down", errorClass: "UnexpectedError" });
    expect(report.lanes).toMatchObject({ "rest-no-auth": "ok", "mcp-no-auth": "down" });
  });

  it("lets one run answer every request for a minute, so it calls out at most once a minute", async () => {
    await get(healthGet());
    now += 30_000;
    await get(healthGet());
    expect(scenario.runs).toBe(1);
    now += 31_000;
    await get(healthGet());
    expect(scenario.runs).toBe(2);
  });

  it("sends its lines out once its run is done", async () => {
    await get(healthGet());
    await Promise.all(kept);
    expect(lines.at(-1)).toMatchObject({ event: "health.done", route: "/api/health" });
    expect(flushedAt).toEqual([lines.length]);
  });
});
