/** Agentic-orchestration diagram for the homepage hero.
 *  Agents ask → the grounded core (retrieve · understand · validate · respond)
 *  answers with access control, citations, and a confidence score → context is
 *  stored to memory and looped back. Pure SVG (vector text scales crisply); a
 *  few dots travel real paths via <animateMotion> — refined, not busy. */

type IconDef = {
  p?: string[];
  c?: [number, number, number][];
  r?: [number, number, number, number, number][];
};

const IC: Record<string, IconDef> = {
  users: { p: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M16 3.128a4 4 0 0 1 0 7.744", "M22 21v-2a4 4 0 0 0-3-3.87"], c: [[9, 7, 4]] },
  headphones: { p: ["M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"] },
  search: { p: ["m21 21-4.34-4.34"], c: [[11, 11, 8]] },
  bot: { p: ["M12 8V4H8", "M2 14h2", "M20 14h2", "M15 13v2", "M9 13v2"], r: [[4, 8, 16, 12, 2]] },
  fileSearch: { p: ["M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z", "M14 2v5a1 1 0 0 0 1 1h5", "M13.3 16.3 15 18"], c: [[11.5, 14.5, 2.5]] },
  brain: { p: ["M12 18V5", "M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4", "M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5", "M17.997 5.125a4 4 0 0 1 2.526 5.77", "M18 18a4 4 0 0 0 2-7.464", "M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517", "M6 18a4 4 0 0 1-2-7.464", "M6.003 5.125a4 4 0 0 0-2.526 5.77"] },
  shieldCheck: { p: ["M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z", "m9 12 2 2 4-4"] },
  message: { p: ["M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z", "M7 11h10", "M7 15h6", "M7 7h8"] },
  lock: { p: ["M7 11V7a5 5 0 0 1 10 0v4"], r: [[3, 11, 18, 11, 2]] },
  quote: { p: ["M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z", "M5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z"] },
  chart: { p: ["M3 3v16a2 2 0 0 0 2 2h16", "M18 17V9", "M13 17V5", "M8 17v-3"] },
};

function Icon({ name, x, y, size, color }: { name: keyof typeof IC; x: number; y: number; size: number; color: string }) {
  const def = IC[name];
  const s = size / 24;
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      {def.p?.map((d) => <path key={d} d={d} />)}
      {def.c?.map(([cx, cy, r], i) => <circle key={`c${i}`} cx={cx} cy={cy} r={r} />)}
      {def.r?.map(([rx, ry, w, h, rr], i) => <rect key={`r${i}`} x={rx} y={ry} width={w} height={h} rx={rr} />)}
    </g>
  );
}

const AGENTS = [
  { icon: "headphones" as const, name: "Support Agent", desc: "Answers customer queries", y: 104 },
  { icon: "search" as const, name: "Research Agent", desc: "Finds insights across docs", y: 228 },
  { icon: "bot" as const, name: "Ops Agent", desc: "Assists internal workflows", y: 352 },
];

const STEPS = [
  { icon: "fileSearch" as const, label: "Retrieve", desc: "Find knowledge", cx: 536 },
  { icon: "brain" as const, label: "Understand", desc: "Extract & reason", cx: 620 },
  { icon: "shieldCheck" as const, label: "Validate", desc: "Check confidence", cx: 704 },
  { icon: "message" as const, label: "Respond", desc: "Cite sources", cx: 788 },
];

const CHIPS = [
  { icon: "lock" as const, label: "Access Control", x: 500 },
  { icon: "quote" as const, label: "Citations", x: 620 },
  { icon: "chart" as const, label: "Confidence", x: 712 },
];

const ASK = [
  "M272 158 C 360 158, 400 258, 474 262",
  "M272 284 C 370 284, 400 272, 474 272",
  "M272 408 C 360 408, 400 286, 474 282",
];
const STORE = "M818 272 C 880 272, 925 250, 980 250";
const LOOP = "M1036 438 C 1036 528, 640 552, 168 500";

function Dot({ path, color, dur, begin, r = 3.4 }: { path: string; color: string; dur: number; begin: number; r?: number }) {
  return (
    <circle r={r} fill={color}>
      <animateMotion dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" path={path} />
      <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.1;0.85;1" dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" />
    </circle>
  );
}

export function AgenticHero({ className = "" }: { className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-line shadow-sm ${className}`}
      style={{ background: "radial-gradient(120% 120% at 50% 0%, var(--canvas) 0%, var(--accent-subtle) 100%)" }}
    >
      <svg viewBox="0 0 1160 570" className="block w-full">
        <defs>
          <linearGradient id="ah-top" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#5eead4" /><stop offset="1" stopColor="#06b6d4" /></linearGradient>
          <linearGradient id="ah-mid" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#38bdf8" /><stop offset="1" stopColor="#2563eb" /></linearGradient>
          <linearGradient id="ah-bot" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3b82f6" /><stop offset="1" stopColor="#1e3a8a" /></linearGradient>
          <filter id="ah-soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="9" /></filter>
          <marker id="ah-arr" markerWidth={7} markerHeight={7} refX={5.5} refY={3} orient="auto"><path d="M0 0 L6 3 L0 6 z" fill="#2563eb" /></marker>
        </defs>

        {/* ——— connectors ——— */}
        <g fill="none">
          {/* return (dotted, behind) */}
          {ASK.map((d, i) => (
            <path key={`rt${i}`} d={d} stroke="#93c5fd" strokeWidth="1.6" strokeDasharray="1.5 6" transform="translate(0 10)" opacity="0.75" />
          ))}
          {/* ask (solid blue) */}
          {ASK.map((d, i) => (
            <path key={`ask${i}`} d={d} stroke="#2563eb" strokeWidth="2" markerEnd="url(#ah-arr)" opacity={i === 1 ? 1 : 0.85} />
          ))}
          {/* store */}
          <path d={STORE} stroke="#2563eb" strokeWidth="2" markerEnd="url(#ah-arr)" />
          {/* context loop */}
          <path d={LOOP} stroke="var(--accent-border)" strokeWidth="1.8" strokeDasharray="1.5 7" />
        </g>

        {/* travelling dots — few and slow */}
        <Dot path={ASK[1]} color="#2563eb" dur={2.2} begin={0} />
        <Dot path={ASK[0]} color="#38bdf8" dur={2.6} begin={0.9} r={3} />
        <Dot path={STORE} color="#16a34a" dur={2.2} begin={0.4} />
        <Dot path={LOOP} color="#38bdf8" dur={5} begin={0} r={3} />

        {/* ——— agents panel ——— */}
        <rect x="36" y="48" width="256" height="436" rx="20" fill="var(--subtle)" stroke="var(--line)" />
        <Icon name="users" x={58} y={66} size={19} color="var(--accent)" />
        <text x="86" y="82" fontSize="16" fontWeight="800" fill="var(--ink)">Agents</text>
        {AGENTS.map((a) => (
          <g key={a.name}>
            <rect x="56" y={a.y} width="216" height="104" rx="14" fill="var(--canvas)" stroke="var(--line-strong)" />
            <circle cx="92" cy={a.y + 40} r="18" fill="var(--accent-subtle)" />
            <Icon name={a.icon} x={80} y={a.y + 28} size={24} color="var(--accent)" />
            <text x="122" y={a.y + 36} fontSize="13.5" fontWeight="700" fill="var(--ink)">{a.name}</text>
            <text x="122" y={a.y + 55} fontSize="10.5" fill="var(--ink-2)">{a.desc}</text>
          </g>
        ))}

        {/* ——— core ——— */}
        <ellipse cx="646" cy="440" rx="180" ry="20" fill="var(--accent)" opacity="0.12" filter="url(#ah-soft)" />
        <rect x="474" y="118" width="344" height="322" rx="24" fill="var(--canvas)" stroke="var(--accent-border)" strokeWidth="1.5" />
        <g transform="translate(618 132) scale(0.9)">
          <rect x="16" y="30" width="34" height="24" rx="7" fill="url(#ah-bot)" />
          <rect x="13" y="20" width="34" height="24" rx="7" fill="url(#ah-mid)" />
          <path d="M17 10 h20 l10 10 v6 a7 7 0 0 1 -7 7 H17 a7 7 0 0 1 -7 -7 v-9 a7 7 0 0 1 7 -7 z" fill="url(#ah-top)" />
        </g>
        <text x="646" y="212" fontSize="17" fontWeight="800" textAnchor="middle" fill="var(--ink)">Knowledge Copilot</text>
        <text x="646" y="232" fontSize="11" textAnchor="middle" fill="var(--ink-2)">Enterprise Knowledge Platform</text>

        {STEPS.map((s) => (
          <g key={s.label}>
            <rect x={s.cx - 19} y="256" width="38" height="38" rx="10" fill="var(--accent-subtle)" />
            <Icon name={s.icon} x={s.cx - 10} y={266} size={20} color="var(--accent)" />
            <text x={s.cx} y="312" fontSize="11" fontWeight="700" textAnchor="middle" fill="var(--ink)">{s.label}</text>
            <text x={s.cx} y="326" fontSize="8.5" textAnchor="middle" fill="var(--ink-3)">{s.desc}</text>
          </g>
        ))}

        <line x1="494" y1="350" x2="798" y2="350" stroke="var(--line)" />
        <rect x="494" y="364" width="304" height="42" rx="12" fill="var(--subtle)" />
        {CHIPS.map((c) => (
          <g key={c.label}>
            <Icon name={c.icon} x={c.x} y={378} size={14} color="var(--ink-3)" />
            <text x={c.x + 20} y="390" fontSize="10.5" fontWeight="600" fill="var(--ink-2)">{c.label}</text>
          </g>
        ))}

        {/* ——— memory ——— */}
        <g transform="translate(980 196)">
          <ellipse cx="56" cy="14" rx="56" ry="14" fill="#e0f2fe" stroke="var(--accent-border)" />
          <path d="M0 14 v96 a56 14 0 0 0 112 0 v-96" fill="#eff6ff" stroke="var(--accent-border)" />
          <path d="M0 14 a56 14 0 0 0 112 0" fill="none" stroke="var(--accent-border)" />
          <ellipse cx="56" cy="62" rx="56" ry="14" fill="none" stroke="var(--accent-border)" opacity="0.5" />
          <Icon name="brain" x={42} y={44} size={28} color="var(--accent)" />
        </g>
        <text x="1036" y="352" fontSize="14" fontWeight="800" textAnchor="middle" fill="var(--ink)">Memory</text>
        <text x="1036" y="370" fontSize="10" textAnchor="middle" fill="var(--ink-2)">Continuous learning</text>
        <text x="1036" y="383" fontSize="10" textAnchor="middle" fill="var(--ink-2)">&amp; knowledge base</text>

        {/* ——— flow labels ——— */}
        <g>
          <rect x="298" y="250" width="112" height="26" rx="13" fill="var(--canvas)" stroke="var(--accent-border)" />
          <text x="354" y="267" fontSize="11" fontWeight="700" textAnchor="middle" fill="#2563eb">1 · Ask / Query</text>
        </g>
        <text x="838" y="238" fontSize="11" fontWeight="700" fill="#2563eb">3 · Store &amp; Update</text>
        <g>
          <rect x="518" y="512" width="124" height="26" rx="13" fill="var(--canvas)" stroke="var(--accent-border)" />
          <text x="580" y="529" fontSize="11" fontWeight="700" textAnchor="middle" fill="#0891b2">2 · Context Loop</text>
        </g>
        <text x="580" y="558" fontSize="10.5" textAnchor="middle" fill="var(--ink-3)">Feedback improves future responses</text>
      </svg>
    </div>
  );
}
