/*
 * tests/stubs/open-meteo-stand-ins.ts: what the Open-Meteo client gets in the tests instead of the network and the
 * Runtime Cache: a fetch that answers from recorded Open-Meteo answers, and a cache in memory.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import type { ResponseCache } from "@/lib/upstream/open-meteo";

const FIXTURES_DIR = path.join(import.meta.dirname, "..", "fixtures", "open-meteo");

/** A recorded Open-Meteo answer, from tests/fixtures/open-meteo/, as text. */
export function readFixture(name: string): string {
  return readFileSync(path.join(FIXTURES_DIR, `${name}.json`), "utf8");
}

/** One answer the fake fetch gives: a fixture's name with its status, or a function for anything else. */
export type FakeAnswer = { fixture: string; status?: number; headers?: Record<string, string> } | (() => Response);

/** A fetch that gives the answers in order, one per call, and records every URL it was asked for, and its headers. */
export function createFakeFetch(answers: FakeAnswer[]): {
  fetch: typeof fetch;
  urls: string[];
  headers: Record<string, string>[];
} {
  const urls: string[] = [];
  const headers: Record<string, string>[] = [];
  const fakeFetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    urls.push(String(input));
    headers.push(Object.fromEntries(new Headers(init?.headers).entries()));
    const answer = answers[urls.length - 1];
    if (answer === undefined) {
      throw new Error(`The fake fetch has no answer for call ${urls.length}: ${String(input)}`);
    }
    if (typeof answer === "function") {
      return answer();
    }
    return new Response(readFixture(answer.fixture), {
      status: answer.status ?? 200,
      headers: { "content-type": "application/json", ...answer.headers },
    });
  };
  return { fetch: fakeFetch as typeof fetch, urls, headers };
}

/** A fetch that never answers: as a real fetch does, it fails with its signal's reason when the signal fires. */
export const hangingFetch = ((_input: string | URL | Request, init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    const signal = init?.signal;
    if (signal?.aborted) {
      reject(signal.reason);
      return;
    }
    signal?.addEventListener("abort", () => reject(signal.reason), { once: true });
  })) as typeof fetch;

/** A cache in memory, with the same calls as the Runtime Cache. */
export function createMemoryCache(): ResponseCache & { entries: Map<string, { value: unknown; ttl: number }> } {
  const entries = new Map<string, { value: unknown; ttl: number }>();
  return {
    entries,
    get: async (key) => entries.get(key)?.value,
    set: async (key, value, { ttl }) => {
      entries.set(key, { value, ttl });
    },
  };
}
