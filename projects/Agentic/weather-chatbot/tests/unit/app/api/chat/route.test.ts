/*
 * tests/unit/app/api/chat/route.test.ts: POST /api/chat refuses a bad request, and says when the chat isn't set up,
 * before any model or weather call: the sentence (with the ref for an error), the request id, and the lines logged.
 * GOOGLE_API_KEY is emptied for these tests, so no real key is ever used. And on Vercel, the route is told when the
 * page goes: vercel.json turns cancellation on for it.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { LogLine } from "@/tests/stubs/log-stand-ins";

// The app's logger, swapped for one whose lines the tests can read.
const { lines } = vi.hoisted(() => ({ lines: [] as LogLine[] }));
vi.mock("@/lib/logger", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/logger")>();
  const write = (line: string) => {
    lines.push(JSON.parse(line) as LogLine);
  };
  return { ...actual, logger: actual.createLogger({ level: "info", destination: { write } }) };
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

type Post = (request: Request) => Promise<Response>;
let post: Post;

beforeAll(async () => {
  // The settings are read when the route's modules load, so the key is emptied first, then the route is loaded.
  vi.stubEnv("GOOGLE_API_KEY", "");
  vi.resetModules();
  post = (await import("@/app/api/chat/route")).POST;
});

beforeEach(() => {
  lines.length = 0;
  kept.length = 0;
});

afterAll(() => {
  vi.unstubAllEnvs();
});

const VERCEL_ID = "iad1::iad1::abcde-1730211234567-f3c2b1a0d9e8";

/** A POST to the chat route, with this body, as it reaches the function on Vercel. */
function chatPost(body: string): Request {
  return new Request("http://localhost/api/chat", {
    method: "POST",
    body,
    headers: { "content-type": "application/json", "x-vercel-id": VERCEL_ID },
  });
}

const QUESTION = "Weather in Paris?";
const VALID_BODY = JSON.stringify({
  id: "chat-1",
  laneId: "rest-no-auth",
  messages: [{ id: "u1", role: "user", parts: [{ type: "text", text: QUESTION }] }],
});

describe("POST /api/chat", () => {
  it("refuses a body that isn't JSON, with 400 and a plain sentence, and logs it as refused", async () => {
    const response = await post(chatPost("not json"));
    expect(response.status).toBe(400);
    expect(await response.text()).toBe("That message can't be sent: its body isn't JSON.");
    expect(lines).toEqual([
      expect.objectContaining({
        level: "info",
        event: "chat.rejected",
        requestId: VERCEL_ID,
        route: "/api/chat",
        errorClass: "InputError",
        message: "its body isn't JSON.",
      }),
    ]);
  });

  it("refuses a lane that doesn't exist, with 400", async () => {
    const response = await post(chatPost(VALID_BODY.replace("rest-no-auth", "fax")));
    expect(response.status).toBe(400);
    expect(await response.text()).toContain("that isn't one of the chat's lanes");
  });

  it("says the chat isn't set up, with 503 and the ref, when GOOGLE_API_KEY is missing", async () => {
    const response = await post(chatPost(VALID_BODY));
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("The assistant isn't set up on this deployment yet. (ref b1a0d9e8)");
    expect(response.headers.get("x-request-id")).toBe(VERCEL_ID);
  });

  it("logs the request, then the failure, each with the request id, chat and lane; never the question", async () => {
    await post(chatPost(VALID_BODY));
    const shared = { requestId: VERCEL_ID, chatId: "chat-1", lane: "rest-no-auth", transport: "rest", auth: "none" };
    expect(lines).toEqual([
      expect.objectContaining({
        ...shared,
        level: "info",
        event: "chat.request",
        messages: 1,
        questionChars: QUESTION.length,
      }),
      expect.objectContaining({ ...shared, level: "error", event: "chat.failed", errorClass: "ConfigError" }),
    ]);
    expect(JSON.stringify(lines)).not.toContain(QUESTION);
    expect(lines[0]).not.toHaveProperty("questionHash");
  });

  it("makes up a request id when Vercel's isn't there, as on a laptop", async () => {
    const request = new Request("http://localhost/api/chat", { method: "POST", body: "not json" });
    const response = await post(request);
    expect(response.headers.get("x-request-id")).toMatch(/^[0-9a-f]{16}$/);
    expect(lines[0]?.requestId).toBe(response.headers.get("x-request-id"));
  });
});

describe("POST /api/chat on Vercel", () => {
  it("logs a page that goes while its message is still being read as stopped, not as a refused message", async () => {
    const page = new AbortController();
    page.abort();
    const going = new DOMException("The page went away.", "AbortError");
    const request = new Request("http://localhost/api/chat", {
      method: "POST",
      body: new ReadableStream({
        start(controller) {
          controller.error(going);
        },
      }),
      duplex: "half",
      signal: page.signal,
      headers: { "content-type": "application/json", "x-vercel-id": VERCEL_ID },
    } as RequestInit);
    await post(request);
    expect(lines).toEqual([expect.objectContaining({ level: "info", event: "chat.aborted", steps: 0 })]);
  });

  it("keeps the function alive until the request's last line, when it ends before the answer starts", async () => {
    const response = await post(chatPost(VALID_BODY));
    expect(response.status).toBe(503);
    expect(kept).toHaveLength(1);
    const still = new Promise((resolve) => setTimeout(() => resolve("still kept alive"), 20));
    expect(await Promise.race([kept[0]?.then(() => "ended"), still])).toBe("ended");
    expect(lines.at(-1)).toMatchObject({ event: "chat.failed", errorClass: "ConfigError" });
  });

  it("is told when the page goes: vercel.json turns cancellation on for this very file, and no other", () => {
    const projectRoot = path.join(import.meta.dirname, "..", "..", "..", "..", "..");
    const vercel: { functions: Record<string, { supportsCancellation?: boolean }> } = JSON.parse(
      readFileSync(path.join(projectRoot, "vercel.json"), "utf8"),
    );
    const cancelled = Object.entries(vercel.functions).filter(([, settings]) => settings.supportsCancellation === true);
    expect(cancelled.map(([file]) => file)).toEqual(["app/api/chat/route.ts"]);
    expect(existsSync(path.join(projectRoot, "app/api/chat/route.ts"))).toBe(true);
  });
});
