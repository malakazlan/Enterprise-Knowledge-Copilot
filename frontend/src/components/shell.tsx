"use client";

/** App shell: top bar (knowledge-base search, workspace nav, invite, account)
 *  over a slim icon sidebar. The ⌘K overlay searches indexed passages — hybrid
 *  dense + BM25 + rerank — not the navigation. */

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  BarChart3,
  Bell,
  Check,
  FileText,
  FlaskConical,
  FolderOpen,
  History,
  KeyRound,
  LifeBuoy,
  LogOut,
  MessagesSquare,
  Moon,
  Plus,
  Search,
  Sun,
  Trash2,
  UserPlus,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import {
  clearTokens,
  deleteThread,
  getAccessToken,
  listReviews,
  listThreads,
  me,
  searchChunks,
} from "@/lib/api";
import type { SearchResultItem, ThreadRead, UserRead } from "@/lib/types";
import { Button, Spinner } from "@/components/ui";
import InviteMemberModal from "@/components/invite";
import { LogoMark } from "@/components/logo";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/ask", label: "Ask", icon: MessagesSquare },
  { href: "/library", label: "Library", icon: FolderOpen },
  { href: "/review", label: "Review Queue", icon: Check },
  { href: "/insights", label: "Insights", icon: BarChart3 },
  { href: "/evals", label: "Evaluations", icon: FlaskConical },
  { href: "/keys", label: "API Keys", icon: KeyRound },
  { href: "/integrations", label: "Integrations", icon: Zap },
];

const THEME_KEY = "ekc.theme";
const ASK_ACTION_KEY = "ekc.ask-action";

export function applyStoredTheme(): void {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") {
    document.documentElement.dataset.theme = stored;
  }
  window.dispatchEvent(new Event("ekc-theme"));
}

function subscribeTheme(onChange: () => void): () => void {
  window.addEventListener("ekc-theme", onChange);
  return () => window.removeEventListener("ekc-theme", onChange);
}

/** Hand an action ("new" | "thread:<id>") to the Ask page, navigating if needed. */
function sendAskAction(push: (href: string) => void, action: string): void {
  sessionStorage.setItem(ASK_ACTION_KEY, action);
  window.dispatchEvent(new Event("ekc-ask-action"));
  push("/ask");
}

export function readAskAction(): string | null {
  const action = sessionStorage.getItem(ASK_ACTION_KEY);
  if (action) sessionStorage.removeItem(ASK_ACTION_KEY);
  return action;
}

// ---- knowledge-base search (⌘K) ----

function KnowledgeSearch({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [index, setIndex] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    const query = q.trim();
    const mine = ++seq.current;
    const timer = setTimeout(() => {
      if (query.length < 2) {
        setResults([]);
        setSearched(false);
        setBusy(false);
        return;
      }
      setBusy(true);
      searchChunks(query, 8)
        .then((res) => {
          if (seq.current !== mine) return;
          setResults(res.results);
          setSearched(true);
          setIndex(0);
        })
        .catch(() => {
          if (seq.current !== mine) return;
          setResults([]);
          setSearched(true);
        })
        .finally(() => {
          if (seq.current === mine) setBusy(false);
        });
    }, q.trim().length < 2 ? 0 : 250);
    return () => clearTimeout(timer);
  }, [q]);

  function open(item: SearchResultItem) {
    onClose();
    router.push(`/viewer/?doc=${item.document_id}&chunk=${item.chunk_id}`);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[14vh]"
      onClick={onClose}
    >
      <div
        className="w-[600px] max-w-[calc(100vw-32px)] overflow-hidden rounded-xl border border-line bg-canvas shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          {busy ? <Spinner /> : <Search size={17} className="shrink-0 text-ink-3" />}
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setIndex((i) => Math.min(i + 1, results.length - 1));
              else if (e.key === "ArrowUp") setIndex((i) => Math.max(i - 1, 0));
              else if (e.key === "Enter" && results[index]) open(results[index]);
              else if (e.key === "Escape") onClose();
            }}
            placeholder="Search the knowledge base…"
            className="min-w-0 flex-1 bg-transparent text-[15px] placeholder:text-ink-3 focus:outline-none"
          />
          <kbd className="rounded border border-line bg-subtle px-1.5 font-mono text-[10px] text-ink-3">
            esc
          </kbd>
        </div>
        <div className="max-h-[46vh] overflow-y-auto p-1.5">
          {results.map((item, i) => (
            <button
              key={item.chunk_id}
              onClick={() => open(item)}
              onMouseEnter={() => setIndex(i)}
              className={`block w-full rounded-lg px-3 py-2.5 text-left ${i === index ? "bg-subtle" : ""}`}
            >
              <span className="flex items-center gap-2">
                <FileText size={13} className="shrink-0 text-ink-3" />
                <span className="truncate font-mono text-[11.5px] font-semibold">
                  {item.filename}
                </span>
                {item.page_number != null && (
                  <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-3">
                    Page {item.page_number}
                  </span>
                )}
              </span>
              <span className="mt-1 line-clamp-2 text-[12px] leading-normal text-ink-2">
                {item.content}
              </span>
            </button>
          ))}
          {q.trim().length < 2 && (
            <p className="px-3 py-4 text-center text-[12.5px] text-ink-3">
              Search every indexed passage across your documents.
            </p>
          )}
          {searched && !busy && results.length === 0 && q.trim().length >= 2 && (
            <p className="px-3 py-4 text-center text-[12.5px] text-ink-3">
              No passages match &ldquo;{q.trim()}&rdquo;.
            </p>
          )}
        </div>
        <p className="border-t border-line px-4 py-2 font-mono text-[10px] text-ink-3">
          Hybrid retrieval · dense + BM25 + cross-encoder rerank · Enter opens the passage
        </p>
      </div>
    </div>
  );
}

// ---- popover chrome ----

function Popover({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute top-[calc(100%+8px)] right-0 z-50 w-[300px] overflow-hidden rounded-xl border border-line bg-canvas shadow-lg">
        {children}
      </div>
    </>
  );
}

function relTime(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}m`;
  if (mins < 1440) return `${Math.round(mins / 60)}h`;
  return `${Math.round(mins / 1440)}d`;
}

function HistoryMenu({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [threads, setThreads] = useState<ThreadRead[] | null>(null);

  const refresh = useCallback(() => {
    listThreads()
      .then(setThreads)
      .catch(() => setThreads([]));
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <Popover onClose={onClose}>
      <p className="border-b border-line px-3.5 py-2.5 text-[11px] font-semibold tracking-[0.1em] text-ink-3 uppercase">
        Recent analyses
      </p>
      <div className="max-h-[320px] overflow-y-auto p-1.5">
        {threads === null && (
          <p className="px-2.5 py-2 text-[12.5px] text-ink-3">Loading…</p>
        )}
        {threads?.map((t) => (
          <div
            key={t.id}
            className="group flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px] hover:bg-subtle"
            onClick={() => {
              onClose();
              sendAskAction((href) => router.push(href), `thread:${t.id}`);
            }}
          >
            <span className="min-w-0 flex-1 truncate">{t.title}</span>
            <span className="shrink-0 font-mono text-[10.5px] text-ink-3">
              {relTime(t.updated_at)}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (!window.confirm("Delete this conversation? Audit records are kept.")) return;
                void deleteThread(t.id)
                  .catch(() => undefined)
                  .then(refresh);
              }}
              className="hidden shrink-0 text-ink-3 group-hover:block hover:text-danger"
              title="Delete conversation"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
        {threads?.length === 0 && (
          <p className="px-2.5 py-2 text-[12.5px] text-ink-3">No analyses yet.</p>
        )}
      </div>
    </Popover>
  );
}

// ---- shell ----

export default function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRead | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [pendingReviews, setPendingReviews] = useState<number | null>(null);
  const dark = useSyncExternalStore(
    subscribeTheme,
    () => document.documentElement.dataset.theme === "dark",
    () => false,
  );

  useEffect(() => {
    applyStoredTheme();
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    me()
      .then((u) => {
        setUser(u);
        // Reviewer/admin only; everyone else just gets no badge.
        listReviews("pending")
          .then((items) => setPendingReviews(items.length))
          .catch(() => setPendingReviews(null));
      })
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
  }, [router]);

  const onKey = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      setSearchOpen((v) => !v);
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
    window.dispatchEvent(new Event("ekc-theme"));
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

  const TOP_NAV = [
    { href: "/insights", label: "Dashboard" },
    { href: "/team", label: "Team" },
  ];

  return (
    <div className="flex min-h-screen">
      {/* ——— Sidebar ——— */}
      <aside className="sticky top-0 flex h-screen w-[228px] shrink-0 flex-col border-r border-line bg-sidebar">
        <div className="flex items-center gap-2.5 px-4 pt-5 pb-4">
          <LogoMark size={30} />
          <span className="truncate text-[13.5px] font-semibold tracking-[-0.01em]">
            Knowledge Copilot
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 pt-1">
          {NAV.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`mb-1 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors ${
                  active
                    ? "bg-accent-subtle font-semibold text-accent"
                    : "font-medium text-ink-2 hover:bg-hover hover:text-ink"
                }`}
              >
                <item.icon size={15} className={active ? "text-accent" : "text-ink-3"} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="px-3 pb-4">
          <Button
            variant="primary"
            className="mb-2 w-full justify-center"
            onClick={() => sendAskAction((href) => router.push(href), "new")}
          >
            <Plus size={14} /> New Analysis
          </Button>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium text-ink-2 transition-colors hover:bg-hover hover:text-ink"
          >
            <LifeBuoy size={15} className="text-ink-3" /> Support
          </a>
        </div>
      </aside>

      {/* ——— Top bar + content ——— */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2.5 border-b border-line bg-page/80 px-5 backdrop-blur-md">
          <button
            onClick={() => setSearchOpen(true)}
            className="flex h-9 w-full max-w-[420px] items-center gap-2 rounded-[10px] border border-line bg-canvas px-3 text-[13px] text-ink-3 shadow-sm transition-all hover:border-line-strong hover:shadow-md"
          >
            <Search size={13} />
            Search knowledge base…
            <kbd className="ml-auto rounded-md border border-line bg-subtle px-1.5 font-mono text-[10px]">
              ⌘K
            </kbd>
          </button>

          <nav className="ml-auto flex items-center gap-1 max-md:hidden">
            {TOP_NAV.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-lg px-2.5 py-1.5 text-[13px] transition-colors ${
                    active
                      ? "font-semibold text-accent"
                      : "font-medium text-ink-2 hover:bg-subtle hover:text-ink"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <span className="h-5 w-px bg-line max-md:hidden" />

          <Link
            href="/review"
            title="Review queue"
            className="relative grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-3 transition-colors hover:bg-subtle hover:text-ink"
          >
            <Bell size={15} />
            {pendingReviews !== null && pendingReviews > 0 && (
              <span className="absolute top-0.5 right-0.5 grid h-[15px] min-w-[15px] place-items-center rounded-full bg-warn px-0.5 font-mono text-[9px] font-bold text-white">
                {pendingReviews > 9 ? "9+" : pendingReviews}
              </span>
            )}
          </Link>

          <div className="relative shrink-0">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              title="Recent analyses"
              className="grid h-8 w-8 place-items-center rounded-lg text-ink-3 transition-colors hover:bg-subtle hover:text-ink"
            >
              <History size={15} />
            </button>
            {historyOpen && <HistoryMenu onClose={() => setHistoryOpen(false)} />}
          </div>

          <button
            onClick={toggleTheme}
            title={dark ? "Switch to light theme" : "Switch to dark theme"}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-3 transition-colors hover:bg-subtle hover:text-ink"
          >
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          {user?.role === "admin" && (
            <Button variant="primary" className="shrink-0" onClick={() => setInviteOpen(true)}>
              <UserPlus size={14} /> Invite Team
            </Button>
          )}

          <div className="relative shrink-0">
            <button
              onClick={() => setAccountOpen((v) => !v)}
              className="grid h-8 w-8 place-items-center rounded-full border border-line-strong bg-hover text-[11px] font-semibold text-ink-2"
              title={user?.email}
            >
              {initials}
            </button>
            {accountOpen && (
              <Popover onClose={() => setAccountOpen(false)}>
                <div className="border-b border-line px-3.5 py-3">
                  <p className="truncate text-[13px] font-semibold">
                    {user?.full_name ?? user?.email ?? "…"}
                  </p>
                  <p className="truncate text-[11.5px] text-ink-3">{user?.email}</p>
                  <p className="mt-1 text-[11px] text-ink-3 capitalize">Role: {user?.role}</p>
                </div>
                <div className="p-1.5">
                  <button
                    onClick={signOut}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-subtle"
                  >
                    <LogOut size={14} className="text-ink-3" /> Sign out
                  </button>
                </div>
              </Popover>
            )}
          </div>
        </header>

        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1240px] px-10 pt-8 pb-24 max-md:px-5">{children}</div>
        </main>
      </div>

      {searchOpen && <KnowledgeSearch onClose={() => setSearchOpen(false)} />}
      {inviteOpen && <InviteMemberModal onClose={() => setInviteOpen(false)} />}
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
