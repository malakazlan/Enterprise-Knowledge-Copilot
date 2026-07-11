"use client";

/** App shell: sidebar navigation, auth guard, theme toggle, command palette. */

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  BarChart3,
  Check,
  FolderOpen,
  KeyRound,
  LogOut,
  MessagesSquare,
  Search,
  SunMoon,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { clearTokens, getAccessToken, me } from "@/lib/api";
import type { UserRead } from "@/lib/types";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/ask", label: "Ask", icon: MessagesSquare },
  { href: "/library", label: "Library", icon: FolderOpen },
  { href: "/review", label: "Review queue", icon: Check },
  { href: "/insights", label: "Insights", icon: BarChart3 },
  { href: "/keys", label: "API keys", icon: KeyRound },
  { href: "/integrations", label: "Integrations", icon: Zap },
];

const THEME_KEY = "ekc.theme";

export function applyStoredTheme(): void {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") {
    document.documentElement.dataset.theme = stored;
  }
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [filter, setFilter] = useState("");
  const [index, setIndex] = useState(0);

  const items = NAV.filter((item) =>
    item.label.toLowerCase().includes(filter.trim().toLowerCase()),
  );

  function go(href: string) {
    onClose();
    router.push(href);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[18vh]"
      onClick={onClose}
    >
      <div
        className="w-[480px] max-w-[calc(100vw-32px)] overflow-hidden rounded-xl border border-line bg-canvas shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
          <Search size={15} className="shrink-0 text-ink-3" />
          <input
            autoFocus
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setIndex((i) => Math.min(i + 1, items.length - 1));
              else if (e.key === "ArrowUp") setIndex((i) => Math.max(i - 1, 0));
              else if (e.key === "Enter" && items[index]) go(items[index].href);
              else if (e.key === "Escape") onClose();
            }}
            placeholder="Go to…"
            className="min-w-0 flex-1 bg-transparent text-sm placeholder:text-ink-3 focus:outline-none"
          />
          <kbd className="rounded border border-line bg-subtle px-1.5 font-mono text-[10px] text-ink-3">
            esc
          </kbd>
        </div>
        <div className="p-1.5">
          {items.map((item, i) => (
            <button
              key={item.href}
              onClick={() => go(item.href)}
              onMouseEnter={() => setIndex(i)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13.5px] ${
                i === index ? "bg-subtle" : ""
              }`}
            >
              <item.icon size={15} className="text-ink-3" />
              {item.label}
            </button>
          ))}
          {items.length === 0 && (
            <p className="px-3 py-2 text-[12.5px] text-ink-3">Nothing matches.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRead | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

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

  const onKey = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      setPaletteOpen((v) => !v);
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

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

        <button
          onClick={() => setPaletteOpen(true)}
          className="mx-0.5 mt-2 flex items-center gap-2 rounded-lg border border-line bg-canvas px-2.5 py-1.5 text-[12.5px] text-ink-3 shadow-sm transition-colors hover:border-line-strong"
        >
          <Search size={13} />
          Search or jump to…
          <kbd className="ml-auto rounded border border-line bg-subtle px-1.5 font-mono text-[10px]">
            ⌘K
          </kbd>
        </button>

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
                <item.icon size={15} className={active ? "text-accent" : "text-ink-3"} />
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
            <SunMoon size={15} />
          </button>
          <button
            onClick={signOut}
            title="Sign out"
            className="grid h-7 w-7 place-items-center rounded-md text-ink-3 transition-colors hover:bg-hover hover:text-ink"
          >
            <LogOut size={15} />
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1160px] px-12 pt-10 pb-24 max-md:px-5">{children}</div>
      </main>

      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
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
