/*
 * tests/unit/instrumentation-client.test.ts: the page starts BotID for the chat's POST where BotID runs (on Vercel),
 * and leaves it off elsewhere, where no challenge is served; and its zod never probes for `new Function`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

const { initBotId } = vi.hoisted(() => ({ initBotId: vi.fn() }));
vi.mock("botid/client/core", () => ({ initBotId }));

afterEach(() => {
  vi.unstubAllEnvs();
  initBotId.mockClear();
});

/** Loads the page's start-up file afresh, with BotID's switch as given. */
async function startPage(botId: "on" | "off"): Promise<void> {
  vi.stubEnv("NEXT_PUBLIC_BOTID", botId);
  vi.resetModules();
  await import("@/instrumentation-client");
}

describe("instrumentation-client.ts", () => {
  it("starts BotID for the chat's POST where BotID runs", async () => {
    await startPage("on");
    expect(initBotId).toHaveBeenCalledWith({ protect: [{ path: "/api/chat", method: "POST" }] });
  });

  it("leaves BotID off elsewhere", async () => {
    await startPage("off");
    expect(initBotId).not.toHaveBeenCalled();
  });

  it("keeps zod from building parsers with `new Function`, which the policy would report", async () => {
    await startPage("off");
    expect(z.config().jitless).toBe(true);
  });
});
