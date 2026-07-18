/** Animated agentic-orchestration scene for the homepage hero.
 *  Agents ask (blue) → the grounded core answers cited (cyan) → context is
 *  written to and recalled from memory (green). Dots travel real SVG paths via
 *  <animateMotion>, so it's pure markup — no JS, works in static export. */

const AGENTS = [
  { emoji: "\u{1F916}", name: "Support Agent", sub: "“Our refund policy?”", y: 40 },
  { emoji: "\u{1F9ED}", name: "Research Agent", sub: "multi-step task", y: 158 },
  { emoji: "⚙️", name: "Ops Agent", sub: "workflow step", y: 276 },
];

// Ask paths: agent right edge -> core left edge.
const ASK = [
  "M188 69 C 300 69, 345 196, 420 205",
  "M188 187 C 300 187, 362 205, 420 210",
  "M188 305 C 300 305, 345 218, 420 214",
];
// Return paths (drawn agent<-core; dots travel core->agent via keyPoints reverse).
const RET = [
  "M420 224 C 345 250, 300 92, 188 82",
  "M420 228 C 345 228, 300 200, 188 198",
  "M420 232 C 345 214, 320 316, 188 314",
];

function FlowDot({ path, color, dur, begin }: { path: string; color: string; dur: number; begin: number }) {
  return (
    <circle r="3.6" fill={color}>
      <animateMotion dur={`${dur}s`} begin={`${begin}s`} repeatCount="indefinite" path={path} />
      <animate
        attributeName="opacity"
        values="0;1;1;0"
        keyTimes="0;0.12;0.85;1"
        dur={`${dur}s`}
        begin={`${begin}s`}
        repeatCount="indefinite"
      />
    </circle>
  );
}

export function AgenticHero({ className = "" }: { className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-line ${className}`}
      style={{
        background:
          "radial-gradient(ellipse 62% 62% at 50% 42%, var(--accent-subtle) 0%, var(--canvas) 72%)",
      }}
    >
      <svg viewBox="0 0 980 380" className="block w-full">
        <defs>
          <linearGradient id="ah-top" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#5eead4" /><stop offset="1" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id="ah-mid" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#38bdf8" /><stop offset="1" stopColor="#2563eb" />
          </linearGradient>
          <linearGradient id="ah-bot" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#3b82f6" /><stop offset="1" stopColor="#1e3a8a" />
          </linearGradient>
          <filter id="ah-soft" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="7" />
          </filter>
          <marker id="ah-arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0 0 L6 3 L0 6 z" fill="var(--ink-3)" />
          </marker>
        </defs>

        {/* connectors */}
        <g fill="none" strokeWidth="1.8">
          {ASK.map((d) => (
            <path key={d} d={d} stroke="var(--accent-border)" markerEnd="url(#ah-arr)" />
          ))}
          {RET.map((d) => (
            <path key={d} d={d} stroke="#22d3ee" strokeOpacity="0.6" strokeDasharray="2 6" />
          ))}
          <path d="M620 190 C 690 190, 720 190, 760 190" stroke="var(--ink-3)" markerEnd="url(#ah-arr)" />
          <path d="M844 286 C 740 322, 560 322, 470 286" stroke="#5eead4" strokeDasharray="2 6" />
        </g>

        {/* travelling dots */}
        {ASK.map((d, i) => (
          <FlowDot key={`a${i}`} path={d} color="#2563eb" dur={1.9} begin={i * 0.4} />
        ))}
        {RET.map((d, i) => (
          <FlowDot key={`r${i}`} path={d} color="#22d3ee" dur={1.9} begin={0.9 + i * 0.4} />
        ))}
        <FlowDot path="M620 190 C 690 190, 720 190, 760 190" color="#16a34a" dur={2.4} begin={1.2} />

        {/* agent cards */}
        {AGENTS.map((a) => (
          <g key={a.name} transform={`translate(20 ${a.y})`}>
            <rect width="168" height="58" rx="14" fill="var(--canvas)" stroke="var(--line-strong)" />
            <circle cx="30" cy="29" r="15" fill="var(--accent-subtle)" />
            <text x="30" y="35" fontSize="16" textAnchor="middle">{a.emoji}</text>
            <text x="54" y="25" fontSize="13" fontWeight="700" fill="var(--ink)">{a.name}</text>
            <text x="54" y="42" fontSize="10.5" fill="var(--ink-2)">{a.sub}</text>
          </g>
        ))}

        {/* core */}
        <g transform="translate(420 106)">
          <ellipse cx="100" cy="150" rx="94" ry="15" fill="var(--accent)" opacity="0.16" filter="url(#ah-soft)" />
          <rect width="200" height="168" rx="22" fill="var(--canvas)" stroke="var(--accent-border)" strokeWidth="1.5" />
          <g transform="translate(72 16) scale(0.86)">
            <rect x="16" y="30" width="34" height="24" rx="7" fill="url(#ah-bot)" />
            <rect x="13" y="20" width="34" height="24" rx="7" fill="url(#ah-mid)" />
            <path d="M17 10 h20 l10 10 v6 a7 7 0 0 1 -7 7 H17 a7 7 0 0 1 -7 -7 v-9 a7 7 0 0 1 7 -7 z" fill="url(#ah-top)" />
          </g>
          <text x="100" y="84" fontSize="14" fontWeight="800" textAnchor="middle" fill="var(--ink)">Knowledge Copilot</text>
          <text x="100" y="101" fontSize="9.5" letterSpacing="0.08em" textAnchor="middle" fill="var(--ink-3)" fontFamily="var(--font-mono)">GROUNDED CONTEXT CORE</text>
          <g transform="translate(18 118)">
            <rect width="164" height="32" rx="9" fill="var(--subtle)" />
            <text x="14" y="20" fontSize="10" fill="var(--ink-2)">retrieve</text>
            <text x="62" y="20" fontSize="10" fill="var(--ink-2)">ground</text>
            <text x="104" y="20" fontSize="10" fill="var(--ink-2)">cite</text>
            <text x="132" y="20" fontSize="10" fontWeight="700" fill="var(--ok)">score</text>
          </g>
        </g>

        {/* memory */}
        <g transform="translate(760 120)">
          <ellipse cx="60" cy="12" rx="58" ry="13" fill="#eafaf3" stroke="#5eead4" />
          <path d="M2 12 v66 a58 13 0 0 0 116 0 v-66" fill="#eafaf3" stroke="#5eead4" />
          <path d="M2 12 a58 13 0 0 0 116 0" fill="none" stroke="#5eead4" />
          <ellipse cx="60" cy="44" rx="58" ry="13" fill="none" stroke="#5eead4" opacity="0.5" />
          <text x="60" y="108" fontSize="13" fontWeight="700" textAnchor="middle" fill="var(--ink)">Memory</text>
          <text x="60" y="124" fontSize="10" textAnchor="middle" fill="var(--ink-2)">remember · recall</text>
        </g>

        {/* labels */}
        <text x="292" y="188" fontSize="10.5" fontWeight="700" fill="#2563eb" fontFamily="var(--font-mono)">1 · ask</text>
        <text x="276" y="322" fontSize="10.5" fontWeight="700" fill="#0891b2" fontFamily="var(--font-mono)">2 · grounded + cited</text>
        <text x="642" y="176" fontSize="10.5" fontWeight="700" fill="#16a34a" fontFamily="var(--font-mono)">3 · keep context</text>
      </svg>
    </div>
  );
}
