/*
 * app/not-found.tsx: the page for an address that doesn't exist, in the app's own design and inside its shell.
 */
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Page not found · Nimbus" };

/** Says the page doesn't exist, and links back to the chat and the documentation. */
export default function NotFoundPage(): ReactNode {
  return (
    <main className="doc">
      <h1>Page not found</h1>
      <p>
        There’s no page at this address. Try the <Link href="/">chat</Link> or the{" "}
        <Link href="/docs">documentation</Link>.
      </p>
    </main>
  );
}
