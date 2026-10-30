/*
 * tests/stubs/apify-stand-ins.ts: what the Apify client gets in the tests instead of the network: a fetch that answers
 * from tests/fixtures/apify/ and records each request it was given. Two fixtures there: Apify's real answer to a fake
 * token (PLAN.md section 3, row 13), and the Actor's answer for Paris in its assumed shape (its README's per-location
 * record, holding Open-Meteo's real Paris answer), until a real run replaces it (step 6).
 */
import { readFileSync } from "node:fs";
import path from "node:path";

const FIXTURES_DIR = path.join(import.meta.dirname, "..", "fixtures", "apify");

/** One answer the fake fetch gives: a fixture's name with its status, or a function for anything else. */
export type ApifyAnswer = { fixture: string; status: number } | (() => Response);

/** One request the fake fetch was given: its address, method, headers and body. */
export type SentRequest = { url: string; method: string; headers: Record<string, string>; body: string };

/** A fetch that gives the answers in order, one per call, and records every request. */
export function createApifyFetch(answers: ApifyAnswer[]): { fetch: typeof fetch; requests: SentRequest[] } {
  const requests: SentRequest[] = [];
  const fakeFetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    requests.push({
      url: String(input),
      method: init?.method ?? "GET",
      headers: Object.fromEntries(new Headers(init?.headers).entries()),
      body: typeof init?.body === "string" ? init.body : "",
    });
    const answer = answers[requests.length - 1];
    if (answer === undefined) {
      throw new Error(`The fake Apify fetch has no answer for call ${requests.length}: ${String(input)}`);
    }
    if (typeof answer === "function") {
      return answer();
    }
    return new Response(readFileSync(path.join(FIXTURES_DIR, `${answer.fixture}.json`), "utf8"), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch: fakeFetch as typeof fetch, requests };
}

/** An error answer in the shape Apify's API documents: a status, and an error's type and message. */
export function apifyError(status: number, type: string, message: string): () => Response {
  return () => new Response(JSON.stringify({ error: { type, message } }), { status });
}
