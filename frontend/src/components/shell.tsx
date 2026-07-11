"use client";

/** App shell: sidebar navigation, auth guard, theme toggle. */

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { clearTokens, getAccessToken, me } from "@/lib/api";
import type { UserRead } from "@/lib/types";

const NAV = [
  { href: "/ask", label: "Ask", icon: "💬" },
  { href: "/library", label: "Library", icon: "🗂" },
  { href: "/review", label: "Review queue", icon: "✓" },
  { href: "/insights", label: "Insights", icon: "📈" },
  { href: "/keys", label: "API keys", icon: "🔑" },
] as const;

const THEME_KEY = "ekc.theme";

export function applyStoredTheme(): void {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") {
    document.documentElement.dataset.theme = stored;
  }
}

export default function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRead | null>(null);

  useEffect(() => {
    applyStoredTheme();
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    me()
      .then(setUser)
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
  }, [router]);

  function toggleTheme() {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
  }

  function signOut() {
    clearTokens();
    router.replace("/login");
  }

  const initials =
    user?.full_name
      ?.split(/\s+/)
      .map((w) => w[0])
      .slice(0, 2)
      .join("")
      .toUpperCase() ??
    user?.email.slice(0, 2).toUpperCase() ??
    "·";

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-[252px] shrink-0 flex-col border-r border-line bg-sidebar p-2.5">
        <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-2">
          <span className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-md bg-accent text-[13px] font-bold text-white">
            K
          </span>
          <span className="truncate text-[13.5px] font-semibold">Knowledge Copilot</span>
        </div>

        <nav className="mt-2 flex-1 overflow-y-auto">
          <p className="px-2.5 pt-3 pb-1 text-[11px] font-semibold text-ink-3">Workspace</p>
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13.5px] transition-colors ${
                  active
                    ? "bg-hover font-semibold text-ink"
                    : "font-medium text-ink-2 hover:bg-hover hover:text-ink"
                }`}
              >
                <span aria-hidden className="w-4 text-center text-[13px]">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2.5 border-t border-line px-1 pt-2.5 pb-1">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-line-strong bg-hover text-[11px] font-semibold text-ink-2">
            {initials}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] leading-tight font-semibold">
              {user?.full_name ?? user?.email ?? "…"}
            </span>
            <span className="block text-[11px] text-ink-3 capitalize">{user?.role ?? ""}</span>
          </span>
          <button
            onClick={toggleTheme}
            title="Toggle theme"
            className="grid h-7 w-7 place-items-center rounded-md text-ink-3 transition-colors hover:bg-hover hover:text-ink"
          >
            ◐
          </button>
          <button
            onClick={signOut}
            title="Sign out"
            className="grid h-7 w-7 place-items-center rounded-md text-ink-3 transition-colors hover:bg-hover hover:text-ink"
          >
            ⏻
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1160px] px-12 pt-10 pb-24 max-md:px-5">{children}</div>
      </main>
    </div>
  );
}

export function PageHead({ title, desc }: { title: string; desc?: string }) {
  return (
    <header className="mb-7">
      <h1 className="text-[26px] font-bold tracking-[-0.02em]">{title}</h1>
      {desc && <p className="mt-2 max-w-[620px] text-sm text-ink-2">{desc}</p>}
    </header>
  );
}
