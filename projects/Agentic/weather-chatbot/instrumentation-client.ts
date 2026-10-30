/*
 * instrumentation-client.ts: runs in the browser before the app does (step 8). It keeps the page's zod from probing
 * for `new Function`; and on Vercel, it starts BotID's invisible check for the chat's POST, so each message carries
 * the answer the route verifies; elsewhere no challenge is served, so BotID stays off.
 */
import { initBotId } from "botid/client/core";
import { z } from "zod";
import { isBotIdOn } from "@/lib/botid";
import { CHAT_API_PATH } from "@/lib/constants";

// zod 4 builds faster parsers with `new Function`, and probes for it first: the Content Security Policy, which allows
// no eval, reports the probe though zod falls back. Without the faster parsers, the page never probes.
z.config({ jitless: true });

if (isBotIdOn()) {
  initBotId({ protect: [{ path: CHAT_API_PATH, method: "POST" }] });
}
