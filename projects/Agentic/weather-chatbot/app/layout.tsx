/*
 * app/layout.tsx: the shell around every page: its language, its title, the left menu and the global styles.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SideMenu } from "@/components/side-menu";
import { config } from "@/lib/config";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Nimbus · Weather chatbot",
  description: "Ask about the weather in plain words, and see every tool call and the path it took.",
};

type RootLayoutProps = { children: ReactNode };

/** The HTML shell shared by every page: the menu on the left, the page beside it. */
export default function RootLayout({ children }: RootLayoutProps): ReactNode {
  // ① Which build is running: the commit Vercel built, else just where it runs ("local" on a laptop).
  const { commit, environment } = config.build;
  const buildLabel = commit ? `Build ${commit} · ${environment}` : `Build: ${environment}`;
  // ② The menu, then the page.
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <SideMenu buildLabel={buildLabel} />
          <div className="shell-content">{children}</div>
        </div>
      </body>
    </html>
  );
}
