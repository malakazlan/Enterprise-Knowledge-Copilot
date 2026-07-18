"use client";

/** Public homepage: the trust-layer pitch, animated. Sections reveal on scroll,
 *  stats count up, an agentic pipeline flows, connectors marquee past. All copy
 *  and numbers match the shipped product and the in-repo Trust Bench. */

import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  Boxes,
  Check,
  Copy,
  FileSearch,
  FileText,
  Layers,
  Lock,
  MessageSquareText,
  Scissors,
  Search,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Users,
  X,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { getAccessToken } from "@/lib/api";
import { BrandHero } from "@/components/brand-hero";
import { LogoMark } from "@/components/logo";

const GITHUB = "https://github.com/malakazlan/Enterprise-Knowledge-Copilot";

function Github({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

// ---- scroll-reveal wrapper ----

function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.classList.add("in");
            obs.unobserve(el);
          }
        }
      },
      { threshold: 0.15 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return (
    <div ref={ref} className={`reveal ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

// ---- count-up stat ----

function CountUp({ to, suffix = "", decimals = 0 }: { to: number; suffix?: string; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [val, setVal] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const obs = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        obs.disconnect();
        const duration = 1100;
        let start = 0;
        const step = (t: number) => {
          if (!start) start = t;
          const p = Math.min((t - start) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          setVal(to * eased);
          if (p < 1) raf = requestAnimationFrame(step);
        };
        raf = requestAnimationFrame(step);
      },
      { threshold: 0.5 },
    );
    obs.observe(el);
    return () => {
      obs.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [to]);
  return (
    <span ref={ref}>
      {val.toFixed(decimals)}
      {suffix}
    </span>
  );
}

const STATS: { node: ReactNode; label: string }[] = [
  { node: <CountUp to={100} suffix="%" />, label: "Grounded answer rate" },
  { node: <CountUp to={100} suffix="%" />, label: "Citations hit the right document" },
  { node: <CountUp to={0} suffix="%" />, label: "False answers on trap questions" },
  { node: <CountUp to={1.4} suffix="s" decimals={1} />, label: "Median answer latency" },
];

// ---- agentic pipeline ----

const PIPELINE = [
  { icon: FileText, label: "Your documents", tone: "cyan" },
  { icon: Scissors, label: "Structure-aware chunking", tone: "cyan" },
  { icon: Boxes, label: "Embed + index", tone: "blue" },
  { icon: Search, label: "Hybrid retrieval + rerank", tone: "blue" },
  { icon: ShieldCheck, label: "Ground, cite & score", tone: "blue" },
  { icon: BadgeCheck, label: "Trusted answer", tone: "green" },
];

function PipelineFlow() {
  return (
    <div className="flex min-w-[720px] items-stretch gap-0 lg:min-w-0">
      {PIPELINE.map((stage, i) => (
        <div key={stage.label} className="flex flex-1 items-center">
          <div className="flex flex-1 flex-col items-center gap-2 text-center">
            <span
              className="grid h-12 w-12 place-items-center rounded-xl border border-line bg-canvas shadow-sm"
              style={{ animation: "node-pulse 2.4s ease-in-out infinite", animationDelay: `${i * 0.3}s` }}
            >
              <stage.icon
                size={19}
                className={
                  stage.tone === "green"
                    ? "text-ok"
                    : stage.tone === "cyan"
                      ? "text-[#0891b2]"
                      : "text-accent"
                }
              />
            </span>
            <span className="max-w-[104px] text-[11.5px] leading-tight font-medium text-ink-2">
              {stage.label}
            </span>
          </div>
          {i < PIPELINE.length - 1 && (
            <span className="flow-track mx-1 self-start" style={{ marginTop: 23 }}>
              <span className="flow-dot" style={{ animationDelay: `${i * 0.3}s` }} />
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- live-behavior demo ----

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
        <span className="ml-2 font-mono text-[10.5px] text-ink-3">knowledge-copilot · live behavior</span>
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
                  <b>Declined.</b> The corpus does not support an answer to this question. No answer
                  is safer than a wrong one.
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

const FEATURES = [
  { icon: ShieldCheck, title: "Confidence scoring", body: "Every answer carries a composite score with retrieval, groundedness, and citation sub-scores." },
  { icon: FileSearch, title: "Inline citations", body: "Each claim links to the exact passage — click through to the highlighted source." },
  { icon: X, title: "Honest refusals", body: "When the evidence isn't there, it declines instead of guessing. No answer beats a wrong one." },
  { icon: Users, title: "Human review queue", body: "Low-confidence answers route to a reviewer; every resolution is audited." },
  { icon: Layers, title: "Agent memory & context", body: "Scoped, expiring memory and token-budgeted context packs your agents can trust." },
  { icon: BadgeCheck, title: "Reproducible evals", body: "Built-in evaluation datasets and the open Trust Bench keep quality measurable." },
];

const CONNECTORS = ["Google Drive", "Notion", "Confluence", "Server folder", "Slack", "SharePoint", "Dropbox", "Gmail"];

const SECURITY = [
  { icon: Lock, label: "Self-hosted — data never leaves your server" },
  { icon: ShieldCheck, label: "OIDC SSO + role-based access, free in OSS" },
  { icon: MessageSquareText, label: "Full audit trail on every answer & review" },
  { icon: Sparkles, label: "CPU-only — no GPU required" },
];

const QUICKSTART = `git clone ${GITHUB}.git
cd Enterprise-Knowledge-Copilot
docker compose -f infra/docker-compose.yml up -d`;

const INTEGRATE = `from openai import OpenAI

client = OpenAI(
    base_url="https://kb.your-company.com/v1",
    api_key="ekc_...",              # a key you mint
)
resp = client.chat.completions.create(
    model="legal",                  # a domain profile
    messages=[{"role": "user", "content": "..."}],
)
# resp.ekc -> { answered, confidence, citations, needs_review }`;

function CodeCard({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative overflow-x-auto rounded-xl bg-[#131312] p-5 text-left shadow-lg">
      <button
        onClick={() => {
          void navigator.clipboard.writeText(code);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="absolute top-3 right-3 grid h-8 w-8 place-items-center rounded-lg text-[#6e6e68] transition-colors hover:bg-[#252523] hover:text-[#ededea]"
        title="Copy"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <p className="mb-2 font-mono text-[10px] tracking-[0.14em] text-[#6e6e68] uppercase">{lang}</p>
      <pre className="font-mono text-[12.5px] leading-relaxed text-[#a5e0b5]">{code}</pre>
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
          <LogoMark size={26} />
          <span className="text-[14px] font-semibold tracking-[-0.01em]">Knowledge Copilot</span>
          <nav className="ml-auto flex items-center gap-1.5">
            <a href="#how" className="rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-subtle hover:text-ink max-sm:hidden">
              How it works
            </a>
            <a href="#features" className="rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-subtle hover:text-ink max-sm:hidden">
              Features
            </a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:bg-subtle hover:text-ink">
              <Github size={14} /> GitHub
            </a>
            <Link href={appHref} className="ml-1 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-accent-hover active:translate-y-px">
              {authed ? "Open App" : "Sign in"} <ArrowRight size={13} />
            </Link>
          </nav>
        </div>
      </header>

      {/* ——— Hero ——— */}
      <section className="relative overflow-hidden px-6 pt-20 pb-16 text-center">
        {/* aurora background */}
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-[-10%] left-[15%] h-[380px] w-[380px] rounded-full bg-[#22d3ee]/20 blur-[90px]" style={{ animation: "aurora 18s ease-in-out infinite" }} />
          <div className="absolute top-[5%] right-[12%] h-[420px] w-[420px] rounded-full bg-accent/20 blur-[100px]" style={{ animation: "aurora 22s ease-in-out infinite reverse" }} />
          <div className="absolute inset-0 opacity-[0.4] [background-image:linear-gradient(var(--line)_1px,transparent_1px),linear-gradient(90deg,var(--line)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
        </div>

        <Reveal>
          <p className="font-mono text-[11px] font-semibold tracking-[0.18em] text-accent uppercase">
            Open source · Apache-2.0 · Self-hosted
          </p>
          <h1 className="mx-auto mt-4 max-w-[740px] text-[46px] leading-[1.08] font-bold tracking-[-0.03em] max-md:text-[32px]">
            Answers your organization can defend.
          </h1>
          <p className="mx-auto mt-5 max-w-[560px] text-[16px] leading-relaxed text-ink-2">
            The trust layer for enterprise knowledge: grounded, cited, confidence-scored answers for
            your team and your agents. When the evidence isn&rsquo;t there, it declines.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <a href="#deploy" className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-[14px] font-semibold text-white shadow-md transition-all hover:bg-accent-hover active:translate-y-px">
              <TerminalSquare size={15} /> Run it in 5 minutes
            </a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-canvas px-5 py-2.5 text-[14px] font-semibold shadow-sm transition-all hover:bg-subtle active:translate-y-px">
              <Github size={15} /> Star on GitHub
            </a>
          </div>
        </Reveal>

        <Reveal delay={120} className="mt-14">
          <DemoPanel />
        </Reveal>
      </section>

      {/* ——— Trust numbers ——— */}
      <section className="border-y border-line bg-canvas px-6 py-12">
        <div className="mx-auto grid max-w-[1000px] grid-cols-4 gap-6 text-center max-md:grid-cols-2">
          {STATS.map((stat, i) => (
            <Reveal key={stat.label} delay={i * 80}>
              <p className="text-[34px] font-bold tracking-[-0.02em] text-accent">{stat.node}</p>
              <p className="mt-1 text-[12.5px] leading-snug text-ink-2">{stat.label}</p>
            </Reveal>
          ))}
        </div>
        <p className="mx-auto mt-8 max-w-[640px] text-center font-mono text-[11px] leading-relaxed text-ink-3">
          Trust Bench v1 — a 35-question public benchmark with deliberate trap questions, versioned in{" "}
          <a href={`${GITHUB}/tree/main/bench`} className="text-accent hover:underline">bench/</a>.
          Self-measured and reproducible against any deployment.
        </p>
      </section>

      {/* ——— How it works (agentic pipeline) ——— */}
      <section id="how" className="px-6 py-20">
        <Reveal className="mx-auto max-w-[760px] text-center">
          <h2 className="text-[28px] font-bold tracking-[-0.02em]">From raw documents to a trusted answer.</h2>
          <p className="mx-auto mt-2.5 max-w-[520px] text-[14px] leading-relaxed text-ink-2">
            Every question runs the same governed pipeline. Nothing is answered that the evidence
            can&rsquo;t support — and every step is inspectable.
          </p>
        </Reveal>
        <Reveal delay={120} className="mx-auto mt-12 max-w-[1000px] overflow-x-auto pb-2">
          <PipelineFlow />
        </Reveal>
        <Reveal delay={200} className="mx-auto mt-10 flex max-w-[720px] flex-wrap items-center justify-center gap-3 text-center">
          <span className="text-[12.5px] text-ink-3">The trusted answer reaches</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-canvas px-3 py-1 text-[12.5px] font-medium shadow-sm">
            <Users size={13} className="text-accent" /> your team, in the app
          </span>
          <span className="text-[12.5px] text-ink-3">and</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-canvas px-3 py-1 text-[12.5px] font-medium shadow-sm">
            <TerminalSquare size={13} className="text-accent" /> your agents, over the API & MCP
          </span>
        </Reveal>
      </section>

      {/* ——— The cube ——— */}
      <section className="border-y border-line bg-canvas px-6 py-20">
        <div className="mx-auto flex max-w-[1060px] items-center gap-14 max-lg:flex-col">
          <Reveal className="w-full max-w-[480px] shrink-0">
            <BrandHero className="w-full" />
          </Reveal>
          <Reveal delay={120} className="min-w-0">
            <h2 className="text-[28px] font-bold tracking-[-0.02em]">One grounded core. Six ways in.</h2>
            <p className="mt-2.5 max-w-[460px] text-[14px] leading-relaxed text-ink-2">
              People ask in the app. Agents call the OpenAI-compatible endpoint or the MCP server.
              Everyone gets the same governed, cited knowledge.
            </p>
            <ul className="mt-6 grid grid-cols-2 gap-x-8 gap-y-4 max-sm:grid-cols-1">
              {[
                ["Knowledge", "Documents, wikis, and drives become one cited corpus"],
                ["Memory", "Scoped, expiring memory your agents can trust"],
                ["Search", "Hybrid retrieval: dense + BM25 + cross-encoder rerank"],
                ["Agents", "OpenAI-compatible API and an MCP server built in"],
                ["Governance", "Confidence gates, human review, full audit trail"],
                ["APIs", "Everything in the UI is a documented REST endpoint"],
              ].map(([name, desc]) => (
                <li key={name} className="flex items-start gap-2.5">
                  <BadgeCheck size={15} className="mt-0.5 shrink-0 text-accent" />
                  <span>
                    <span className="block text-[13.5px] font-semibold">{name}</span>
                    <span className="block text-[12.5px] leading-snug text-ink-2">{desc}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </section>

      {/* ——— Feature grid ——— */}
      <section id="features" className="px-6 py-20">
        <Reveal className="mx-auto max-w-[720px] text-center">
          <h2 className="text-[28px] font-bold tracking-[-0.02em]">A trust layer, not just a chatbot.</h2>
          <p className="mx-auto mt-2.5 max-w-[500px] text-[14px] leading-relaxed text-ink-2">
            The things enterprises actually need before they let AI touch their knowledge.
          </p>
        </Reveal>
        <div className="mx-auto mt-12 grid max-w-[1060px] grid-cols-3 gap-4 max-md:grid-cols-1">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 80}>
              <div className="h-full rounded-2xl border border-line bg-canvas p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-accent-border hover:shadow-md">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-subtle text-accent">
                  <f.icon size={18} />
                </span>
                <h3 className="mt-3.5 text-[15px] font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{f.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ——— Connectors marquee ——— */}
      <section className="border-y border-line bg-canvas py-12">
        <Reveal className="px-6 text-center">
          <h2 className="text-[20px] font-bold tracking-[-0.02em]">Connect your sources once.</h2>
          <p className="mx-auto mt-2 max-w-[460px] text-[13px] text-ink-2">
            Click-to-connect OAuth for Drive and Notion, an API-token for Confluence, folders for
            everything else. Re-syncs are idempotent.
          </p>
        </Reveal>
        <div className="relative mt-8 overflow-hidden [mask-image:linear-gradient(90deg,transparent,black_12%,black_88%,transparent)]">
          <div className="flex w-max gap-3" style={{ animation: "marquee 26s linear infinite" }}>
            {[...CONNECTORS, ...CONNECTORS].map((name, i) => (
              <span key={i} className="flex items-center gap-2 rounded-xl border border-line bg-page px-4 py-2.5 text-[13px] font-medium whitespace-nowrap shadow-sm">
                <span className="h-2 w-2 rounded-full bg-accent-border" /> {name}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ——— Integrate (code) ——— */}
      <section className="px-6 py-20">
        <div className="mx-auto grid max-w-[1060px] items-center gap-12 lg:grid-cols-2">
          <Reveal>
            <p className="font-mono text-[11px] font-semibold tracking-[0.16em] text-accent uppercase">For your agents</p>
            <h2 className="mt-3 text-[28px] font-bold tracking-[-0.02em]">Point any agent at your knowledge.</h2>
            <p className="mt-2.5 max-w-[440px] text-[14px] leading-relaxed text-ink-2">
              One line changes the base URL. Your existing OpenAI-SDK code keeps working — but now
              answers are grounded in your documents and carry trust signals your workflow can branch
              on. There&rsquo;s an MCP server too, for Claude and other MCP clients.
            </p>
            <ul className="mt-5 space-y-2.5">
              {[
                "Grounded, cited completions at /v1/chat/completions",
                "Trust signals ride in the ekc extension object",
                "MCP tools: ask, search, remember, recall, write_knowledge",
              ].map((line) => (
                <li key={line} className="flex items-start gap-2.5 text-[13.5px]">
                  <Check size={15} className="mt-0.5 shrink-0 text-ok" /> {line}
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={120}>
            <CodeCard code={INTEGRATE} lang="python" />
          </Reveal>
        </div>
      </section>

      {/* ——— Security strip ——— */}
      <section className="border-y border-line bg-canvas px-6 py-12">
        <div className="mx-auto flex max-w-[1000px] flex-wrap items-center justify-center gap-x-8 gap-y-4 text-center">
          {SECURITY.map(({ icon: Icon, label }) => (
            <span key={label} className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
              <Icon size={15} className="text-accent" /> {label}
            </span>
          ))}
        </div>
      </section>

      {/* ——— Deploy ——— */}
      <section id="deploy" className="px-6 py-20 text-center">
        <Reveal>
          <h2 className="text-[28px] font-bold tracking-[-0.02em]">Yours in three lines.</h2>
          <p className="mx-auto mt-2.5 max-w-[520px] text-[14px] leading-relaxed text-ink-2">
            CPU-only Docker Compose: Postgres, Redis, Qdrant, OCR, Office parsing, and the web app.
            No API keys required — local models by default, cloud LLMs one env var away.
          </p>
        </Reveal>
        <Reveal delay={120} className="mx-auto mt-8 max-w-[640px]">
          <CodeCard code={QUICKSTART} lang="bash" />
          <p className="mt-4 font-mono text-[11px] text-ink-3">
            Open http://localhost:8000 — the first account registered becomes the administrator.
          </p>
        </Reveal>
      </section>

      {/* ——— Final CTA ——— */}
      <section className="px-6 pb-24">
        <Reveal className="mx-auto max-w-[900px] overflow-hidden rounded-3xl border border-line bg-canvas px-8 py-14 text-center shadow-lg">
          <LogoMark size={44} />
          <h2 className="mt-5 text-[30px] font-bold tracking-[-0.02em]">Give your knowledge a conscience.</h2>
          <p className="mx-auto mt-3 max-w-[480px] text-[14.5px] leading-relaxed text-ink-2">
            Grounded answers, honest refusals, and a paper trail — for the people and the agents that
            depend on what your organization knows.
          </p>
          <div className="mt-7 flex items-center justify-center gap-3">
            <Link href={appHref} className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-[14px] font-semibold text-white shadow-md transition-all hover:bg-accent-hover active:translate-y-px">
              {authed ? "Open the app" : "Get started"} <ArrowRight size={14} />
            </Link>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-page px-5 py-2.5 text-[14px] font-semibold shadow-sm transition-all hover:bg-subtle active:translate-y-px">
              <Github size={15} /> Star on GitHub
            </a>
          </div>
        </Reveal>
      </section>

      {/* ——— Footer ——— */}
      <footer className="border-t border-line px-6 py-10">
        <div className="mx-auto flex max-w-[1120px] items-center gap-4 text-[12.5px] text-ink-3 max-sm:flex-col">
          <span className="flex items-center gap-2">
            <LogoMark size={20} /> Enterprise Knowledge Copilot · Apache-2.0
          </span>
          <nav className="ml-auto flex items-center gap-5 max-sm:ml-0">
            <a href="#how" className="hover:text-ink">How it works</a>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="hover:text-ink">GitHub</a>
            <a href="/docs" className="hover:text-ink">API reference</a>
            <Link href="/login" className="hover:text-ink">Sign in</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
