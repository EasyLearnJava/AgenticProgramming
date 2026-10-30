/*
 * tests/unit/log-shipper.test.ts: the log lines go to Axiom in one batch when asked, with the token, as NDJSON; a batch
 * Axiom doesn't take is reported, never thrown; and past the limit, lines are dropped and counted.
 */
import { describe, expect, it } from "vitest";
import { createLogShipper, toAxiomIngestUrl } from "@/lib/log-shipper";

const TOKEN = "xaat-test-token-not-real";

/** A shipper whose Axiom is a stand-in: each request it gets, each reply it gives, and each line reported on stderr. */
function shipperWith(answer: () => Promise<Response>, maxPendingLines = 1000) {
  const requests: { url: string; init: RequestInit }[] = [];
  const replies: Response[] = [];
  const reports: string[] = [];
  const shipper = createLogShipper({
    dataset: "weather-chatbot",
    token: TOKEN,
    maxPendingLines,
    fetch: (async (url: string, init: RequestInit) => {
      requests.push({ url, init });
      const reply = await answer();
      replies.push(reply);
      return reply;
    }) as typeof fetch,
    report: (line) => reports.push(line),
  });
  return { shipper, requests, replies, reports };
}

describe("createLogShipper", () => {
  it("sends the kept lines to Axiom's US ingest in one batch, with the token; then has nothing to send", async () => {
    const { shipper, requests, replies } = shipperWith(async () => new Response("{}", { status: 200 }));
    shipper.write('{"event":"chat.request"}\n');
    shipper.write('{"event":"chat.done"}\n');
    await shipper.flush();
    await shipper.flush();
    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe(toAxiomIngestUrl("weather-chatbot"));
    expect(requests[0]?.url).toBe("https://us-east-1.aws.edge.axiom.co/v1/ingest/weather-chatbot?timestamp-field=ts");
    expect(requests[0]?.init.headers).toEqual({
      authorization: `Bearer ${TOKEN}`,
      "content-type": "application/x-ndjson",
    });
    expect(requests[0]?.init.body).toBe('{"event":"chat.request"}\n{"event":"chat.done"}\n');
    // The reply is let go once its status is read, so its connection is free for the next batch.
    expect(replies.map((reply) => reply.bodyUsed)).toEqual([true]);
  });

  it("reports a batch Axiom refuses, or can't be reached for, and never throws", async () => {
    const refused = shipperWith(async () => new Response("no", { status: 403 }));
    refused.shipper.write('{"event":"chat.done"}\n');
    await expect(refused.shipper.flush()).resolves.toBeUndefined();
    expect(refused.reports.map((line) => JSON.parse(line))).toEqual([
      { level: "warn", event: "axiom.failed", httpStatus: 403, lines: 1 },
    ]);
    expect(refused.replies.map((reply) => reply.bodyUsed)).toEqual([true]);
    const unreachable = shipperWith(async () => {
      throw new TypeError("fetch failed");
    });
    unreachable.shipper.write('{"event":"chat.done"}\n');
    await expect(unreachable.shipper.flush()).resolves.toBeUndefined();
    expect(JSON.parse(unreachable.reports[0] ?? "{}")).toMatchObject({ event: "axiom.failed", reason: "TypeError" });
    expect(JSON.stringify(unreachable.reports)).not.toContain(TOKEN);
  });

  it("keeps at most its limit of lines between batches, and says how many it dropped", async () => {
    const { shipper, requests, reports } = shipperWith(async () => new Response("{}", { status: 200 }), 2);
    for (const event of ["a", "b", "c", "d"]) {
      shipper.write(`{"event":"${event}"}\n`);
    }
    await shipper.flush();
    expect(requests[0]?.init.body).toBe('{"event":"a"}\n{"event":"b"}\n');
    expect(reports.map((line) => JSON.parse(line))).toEqual([{ level: "warn", event: "axiom.dropped", lines: 2 }]);
  });
});
