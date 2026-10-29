/*
 * app/page.tsx: the home page. For now, a hello card in the chat's design; the chat itself comes in the next steps.
 */
import type { ReactNode } from "react";

/** The hello page: the chat card, with one message from the bot. */
export default function HomePage(): ReactNode {
  return (
    <main className="page">
      <section className="card" aria-labelledby="card-title">
        <h1 id="card-title" className="card-title">
          Nimbus (Weather)
        </h1>
        <p className="bubble bubble-bot">
          Hello! I’m Nimbus. Soon you’ll ask me about the weather here, and see every tool call I make to answer.
        </p>
        <p className="note">Coming next: the chat, through four lanes: REST or MCP, with or without auth.</p>
      </section>
    </main>
  );
}
