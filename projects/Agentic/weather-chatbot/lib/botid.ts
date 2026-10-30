/*
 * lib/botid.ts: whether BotID runs, one answer for the page and the chat route (step 8). next.config.ts sets
 * NEXT_PUBLIC_BOTID when the app is built, "on" only on Vercel, which serves BotID's challenge, and Next.js writes that
 * value into the page's code and the route's alike, so the two can't disagree.
 */

/** Whether BotID checks the chat's requests: on Vercel only. */
export function isBotIdOn(): boolean {
  return process.env.NEXT_PUBLIC_BOTID === "on";
}
