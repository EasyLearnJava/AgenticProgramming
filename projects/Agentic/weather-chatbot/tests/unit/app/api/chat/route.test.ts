/*
 * tests/unit/app/api/chat/route.test.ts: POST /api/chat refuses a bad request, and says when the chat isn't set up,
 * before any model or weather call: the sentence (with the ref for an error), the request id, and the lines logged.
 * GOOGLE_API_KEY is emptied for these tests, so no real key is ever used.
 */
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

  it("refuses a lane that isn't live yet, with 400", async () => {
    const response = await post(chatPost(VALID_BODY.replace("rest-no-auth", "mcp-auth")));
    expect(response.status).toBe(400);
    expect(await response.text()).toContain("that lane isn't live yet");
  });

  it("says the chat isn't set up, with 503 and the ref, when GOOGLE_API_KEY is missing", async () => {
    const response = await post(chatPost(VALID_BODY));
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("The assistant isn't set up on this deployment yet. (ref b1a0d9e8)");
    expect(response.headers.get("x-request-id")).toBe(VERCEL_ID);
  });

  it("logs the request, then the failure, each with the request id, the chat and the lane; never the question", async () => {
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
