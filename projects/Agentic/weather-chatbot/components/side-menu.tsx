/*
 * components/side-menu.tsx: the menu on the left: the chat, the documentation, the system design, the issues log, the
 * interview guide, and which build is running.
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

type SideMenuProps = { buildLabel: string };

const MENU_ITEMS = [
  { href: "/", label: "Chat" },
  { href: "/docs", label: "Documentation" },
  { href: "/system-design", label: "System design" },
  { href: "/issues", label: "Issues and fixes" },
  { href: "/interview", label: "Interview guide" },
] as const;

/** How a menu link relates to the address: it's the page itself, a section the page is in, or neither. */
function toAriaCurrent(pathname: string, href: string): "page" | "true" | undefined {
  if (pathname === href) return "page";
  if (href !== "/" && pathname.startsWith(`${href}/`)) return "true";
  return undefined;
}

/** The left menu; the current page (or section) is marked, for screen readers too. */
export function SideMenu({ buildLabel }: SideMenuProps): ReactNode {
  const pathname = usePathname();
  return (
    <nav className="side-menu" aria-label="Main">
      <p className="side-menu-brand">Nimbus</p>
      <ul className="side-menu-items">
        {MENU_ITEMS.map((item) => (
          <li key={item.href}>
            <Link href={item.href} className="side-menu-link" aria-current={toAriaCurrent(pathname, item.href)}>
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
      <p className="side-menu-build">{buildLabel}</p>
    </nav>
  );
}
