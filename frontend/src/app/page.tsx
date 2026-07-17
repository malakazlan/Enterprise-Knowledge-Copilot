"use client";

/** Public homepage: the trust-layer pitch. The demo panel replays real
 *  product behavior (states, copy, and numbers match the shipped app and the
 *  in-repo Trust Bench); the stats strip is the latest bench run. */

import Link from "next/link";
import {
  ArrowRight,
  BookOpenCheck,
  Check,
  Copy,
  FileSearch,
  ShieldCheck,
  TerminalSquare,
  X,
} from "lucide-react";

function Github({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}
import { useEffect, useState } from "react";

import { getAccessToken } from "@/lib/api";
import { BrandHero } from "@/components/brand-hero";
import { LogoMark } from "@/components/logo";

const GITHUB = "https://github.com/malakazlan/Enterprise-Knowledge-Copilot";

const STATS = [
  { value: "100%", label: "Grounded answer rate" },
  { value: "100%", label: "Citations hit the right document" },
  { value: "0%", label: "False answers on trap questions" },
  { value: "1.4s", label: "Median answer latency" },
];

const CUBE_FACETS = [
  { name: "Knowledge", desc: "Documents, wikis, and drives become one cited corpus" },
  { name: "Memory", desc: "Scoped, expiring memory your agents can trust" },
  { name: "Search", desc: "Hybrid retrieval: dense + BM25 + cross-encoder rerank" },
  { name: "Agents", desc: "OpenAI-compatible API and an MCP server built in" },
  { name: "Governance", desc: "Confidence gates, human review, full audit trail" },
  { name: "APIs", desc: "Everything in the UI is a documented REST endpoint" },
];

const QUICKSTART = `git clone ${GITHUB}.git
cd Enterprise-Knowledge-Copilot
docker compose -f infra/docker-compose.yml up -d`;

function DemoPanel() {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setStage((s) => (s + 1) % 4), 3200);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="mx-auto w-full max-w-[680px] rounded-2xl border border-line bg-canvas p-5 text-left shadow-lg">
      <div className="mb-4 flex items-center gap-2 border-b border-line pb-3">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/40" />
        <span className="h-2.5 w-2.5 rounded-full bg-warn/40" />
        <span className="h-2.5 w-2.5 rounded-full bg-ok/40" />
        <span className="ml-2 font-mono text-[10.5px] text-ink-3">
          knowledge-copilot · live behavior
        </span>
      </div>

      {stage < 2 ? (
        <div key="grounded" className="animate-rise">
          <div className="mb-3 flex justify-end">
            <p className="rounded-[12px_12px_4px_12px] border border-line bg-subtle px-3.5 py-2 text-[13px]">
              What monthly uptime does our SLA commit to?
            </p>
          </div>
          {stage === 0 ? (
            <p className="flex items-center gap-2 text-[13px] text-ink-3">
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
              Searching 5 documents…
            </p>
          ) : (
            <div className="animate-rise rounded-xl border border-line bg-canvas shadow-sm">
              <div className="flex items-center gap-2 border-b border-line px-4 py-2">
                <ShieldCheck size={13} className="text-accent" />
                <span className="text-[12px] font-semibold">Intelligence Report</span>
                <span className="ml-auto rounded-full bg-ok-subtle px-2 py-0.5 text-[10.5px] font-bold text-ok">
                  Confidence: 99%
                </span>
              </div>
              <p className="px-4 py-3 text-[13px] leading-relaxed">
                The platform commits to <b>99.95% monthly uptime</b> for all paid plans
                <span className="mx-1 inline-flex h-[16px] min-w-[16px] items-center justify-center rounded-[4px] bg-accent-subtle px-1 font-mono text-[10px] font-semibold text-accent">
                  1
                </span>
                .
              </p>
              <p className="flex items-center gap-1.5 border-t border-line px-4 py-2 font-mono text-[10.5px] text-ink-3">
                <FileSearch size={11} /> [1] meridian-sla.md, Availability
              </p>
            </div>
          )}
        </div>
      ) : (
        <div key="refusal" className="animate-rise">
          <div className="mb-3 flex justify-end">
            <p className="rounded-[12px_12px_4px_12px] border border-line bg-subtle px-3.5 py-2 text-[13px]">
              What was our revenue last quarter?
            </p>
          </div>
          {stage === 2 ? (
            <p className="flex items-center gap-2 text-[13px] text-ink-3">
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
              Searching 5 documents…
            </p>
          ) : (
            <div className="animate-rise rounded-xl border border-danger/25 bg-danger-subtle/60 px-4 py-3">
              <p className="flex items-start gap-2 text-[13px] leading-relaxed">
                <X size={14} className="mt-0.5 shrink-0 text-danger" />
                <span>
                  <b>Declined.</b> The corpus does not support an answer to this question. No
                  answer is safer than a wrong one.
                </span>
              </p>
            </div>
          )}
        </div>
      )}

      <p className="mt-4 border-t border-line pt-2.5 text-center font-mono text-[10px] text-ink-3">
        Both behaviors are measured — see the numbers below.
      </p>
    </div>
  );
}

function CopyBlock() {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative mx-auto max-w-[640px] overflow-x-auto rounded-xl bg-[#131312] p-5 text-left shadow-lg">
      <button
        onClick={() => {
          void navigator.clipboard.writeText(QUICKSTART);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="absolute top-3 right-3 grid h-8 w-8 place-items-center rounded-lg text-[#6e6e68] transition-colors hover:bg-[#252523] hover:text-[#ededea]"
        title="Copy"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <pre className="font-mono text-[12.5px] leading-relaxed text-[#a5e0b5]">{QUICKSTART}</pre>
    </div>
  );
}

export default function HomePage() {
  const [authed, setAuthed] = useState(false);
  useEffect(() => {
    setTimeout(() => setAuthed(Boolean(getAccessToken())), 0);
  }, []);
  const appHref = authed ? "/ask" : "/login";

  return (
    <div className="min-h-screen bg-page">
      {/* ——— Nav ——— */}
      <header className="sticky top-0 z-30 border-b border-line bg-page/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1120px] items-center gap-3 px-6">
          <LogoMark size={28} />
          <span className="text-[14px] font-semibold tracking-[-0.01em]">Knowledge Copilot</span>
          <nav className="ml-auto flex items-center gap-1.5">
            <a
              href={`${GITHUB}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-subtle hover:text-ink"
            >
              <Github size={14} /> GitHub
            </a>
            <a
              href="/docs"
              className="rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-subtle hover:text-ink max-sm:hidden"
            >
              API docs
            </a>
            <Link
              href={appHref}
              className="ml-1 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-accent-hover active:translate-y-px"
            >
              {authed ? "Open App" : "Sign in"} <ArrowRight size={13} />
            </Link>
          </nav>
        </div>
      </header>

      {/* ——— Hero ——— */}
      <section className="px-6 pt-20 pb-14 text-center">
        <p className="font-mono text-[11px] font-semibold tracking-[0.18em] text-accent uppercase">
          Open source · Apache-2.0 · Self-hosted
        </p>
        <h1 className="mx-auto mt-4 max-w-[720px] text-[44px] leading-[1.1] font-bold tracking-[-0.03em] max-md:text-[32px]">
          Answers your organization can defend.
        </h1>
        <p className="mx-auto mt-5 max-w-[560px] text-[16px] leading-relaxed text-ink-2">
          The trust layer for enterprise knowledge: grounded, cited, confidence-scored answers
          for your team and your agents. When the evidence isn&rsquo;t there, it declines.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <a
            href="#deploy"
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-[14px] font-semibold text-white shadow-md transition-all hover:bg-accent-hover active:translate-y-px"
          >
            <TerminalSquare size={15} /> Run it in 5 minutes
          </a>
          <a
            href={GITHUB}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-canvas px-5 py-2.5 text-[14px] font-semibold shadow-sm transition-all hover:bg-subtle active:translate-y-px"
          >
            <Github size={15} /> Star on GitHub
          </a>
        </div>
        <div className="mt-14">
          <DemoPanel />
        </div>
      </section>

      {/* ——— Trust numbers ——— */}
      <section className="border-y border-line bg-canvas px-6 py-12">
        <div className="mx-auto grid max-w-[1000px] grid-cols-4 gap-6 text-center max-md:grid-cols-2">
          {STATS.map((stat) => (
            <div key={stat.label}>
              <p className="text-[34px] font-bold tracking-[-0.02em] text-accent">{stat.value}</p>
              <p className="mt-1 text-[12.5px] leading-snug text-ink-2">{stat.label}</p>
            </div>
          ))}
        </div>
        <p className="mx-auto mt-8 max-w-[640px] text-center font-mono text-[11px] leading-relaxed text-ink-3">
          Trust Bench v1 — a 25-question public benchmark with deliberate trap questions, versioned
          in{" "}
          <a href={`${GITHUB}/tree/main/bench`} className="text-accent hover:underline">
            bench/
          </a>
          . Self-measured and reproducible against any deployment — run it yourself.
        </p>
      </section>

      {/* ——— The cube ——— */}
      <section className="px-6 py-20">
        <div className="mx-auto flex max-w-[1060px] items-center gap-14 max-lg:flex-col">
          <BrandHero className="w-full max-w-[480px] shrink-0" />
          <div className="min-w-0">
            <h2 className="text-[28px] font-bold tracking-[-0.02em]">
              One grounded core. Six ways in.
            </h2>
            <p className="mt-2.5 max-w-[460px] text-[14px] leading-relaxed text-ink-2">
              People ask in the app. Agents call the OpenAI-compatible endpoint or the MCP
              server. Everyone gets the same governed, cited knowledge.
            </p>
            <ul className="mt-6 grid grid-cols-2 gap-x-8 gap-y-4 max-sm:grid-cols-1">
              {CUBE_FACETS.map((facet) => (
                <li key={facet.name} className="flex items-start gap-2.5">
                  <BookOpenCheck size={15} className="mt-0.5 shrink-0 text-accent" />
                  <span>
                    <span className="block text-[13.5px] font-semibold">{facet.name}</span>
                    <span className="block text-[12.5px] leading-snug text-ink-2">
                      {facet.desc}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ——— Deploy ——— */}
      <section id="deploy" className="border-t border-line bg-canvas px-6 py-20 text-center">
        <h2 className="text-[28px] font-bold tracking-[-0.02em]">Yours in three lines.</h2>
        <p className="mx-auto mt-2.5 max-w-[520px] text-[14px] leading-relaxed text-ink-2">
          CPU-only Docker Compose: Postgres, Redis, Qdrant, OCR, Office parsing, and the web app.
          No GPU. No API keys required — local models by default, cloud LLMs one env var away.
        </p>
        <div className="mt-8">
          <CopyBlock />
        </div>
        <p className="mt-4 font-mono text-[11px] text-ink-3">
          Open http://localhost:8000 — the first account registered becomes the administrator.
        </p>
      </section>

      {/* ——— Footer ——— */}
      <footer className="border-t border-line px-6 py-10">
        <div className="mx-auto flex max-w-[1120px] items-center gap-4 text-[12.5px] text-ink-3 max-sm:flex-col">
          <span className="flex items-center gap-2">
            <LogoMark size={20} /> Enterprise Knowledge Copilot · Apache-2.0
          </span>
          <nav className="ml-auto flex items-center gap-5 max-sm:ml-0">
            <a href={GITHUB} target="_blank" rel="noreferrer" className="hover:text-ink">
              GitHub
            </a>
            <a href="/docs" className="hover:text-ink">
              API reference
            </a>
            <Link href="/login" className="hover:text-ink">
              Sign in
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
