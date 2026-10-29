/*
 * app/layout.tsx: the shell around every page: its language, its title and the global styles.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Nimbus · Weather chatbot",
  description: "Ask about the weather in plain words, and see every tool call and the path it took.",
};

type RootLayoutProps = { children: ReactNode };

/** The HTML shell shared by every page. */
export default function RootLayout({ children }: RootLayoutProps): ReactNode {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
