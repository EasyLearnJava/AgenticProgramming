/*
 * tests/unit/app/api/chat/route.test.ts: POST /api/chat refuses a bad request, and says when the chat isn't set up,
 * before any model or weather call. GOOGLE_API_KEY is emptied for these tests, so no real key is ever used.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

type Post = (request: Request) => Promise<Response>;
let post: Post;

beforeAll(async () => {
  // The settings are read when the route's modules load, so the key is emptied first, then the route is loaded.
  vi.stubEnv("GOOGLE_API_KEY", "");
  vi.resetModules();
  post = (await import("@/app/api/chat/route")).POST;
});

afterAll(() => {
  vi.unstubAllEnvs();
});

/** A POST to the chat route, with this body. */
function chatPost(body: string): Request {
  return new Request("http://localhost/api/chat", {
    method: "POST",
    body,
    headers: { "content-type": "application/json" },
  });
}

const VALID_BODY = JSON.stringify({
  id: "chat-1",
  laneId: "rest-no-auth",
  messages: [{ id: "u1", role: "user", parts: [{ type: "text", text: "Weather in Paris?" }] }],
});

describe("POST /api/chat", () => {
  it("refuses a body that isn't JSON, with 400 and a plain sentence", async () => {
    const response = await post(chatPost("not json"));
    expect(response.status).toBe(400);
    expect(await response.text()).toBe("That message can't be sent: its body isn't JSON.");
  });

  it("refuses a lane that isn't live yet, with 400", async () => {
    const response = await post(chatPost(VALID_BODY.replace("rest-no-auth", "mcp-auth")));
    expect(response.status).toBe(400);
    expect(await response.text()).toContain("that lane isn't live yet");
  });

  it("says the chat isn't set up, with 503, when GOOGLE_API_KEY is missing", async () => {
    const response = await post(chatPost(VALID_BODY));
    expect(response.status).toBe(503);
    expect(await response.text()).toBe("The assistant isn't set up on this deployment yet.");
  });
});
