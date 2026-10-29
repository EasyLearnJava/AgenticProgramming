/*
 * lib/utils.ts: every shared helper function: general-purpose, pure, and safe in the browser as well as on the server.
 */
import type { WireRequest } from "@/lib/types";

/** Writes a request as it goes over the wire: the request line, the headers, then a blank line and the body. */
export function toWireText(request: WireRequest): string {
  const headerLines = Object.entries(request.headers).map(([name, value]) => `${name}: ${value}`);
  const head = [`${request.method} ${request.url}`, ...headerLines].join("\n");
  return request.body === undefined ? head : `${head}\n\n${request.body}`;
}

/** The host part of a URL, as written: "https://api.apify.com/v2/acts" → "api.apify.com". */
export function toHost(url: string): string {
  return url.replace(/^[a-z]+:\/\//i, "").split(/[/?#]/, 1)[0] ?? url;
}
