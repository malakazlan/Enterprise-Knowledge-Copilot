/** Brand hero: the EKC cube — knowledge core with six capability satellites.
 *  Hand-drawn SVG (isometric cube, glow filters, hex nodes). Every satellite
 *  is a real subsystem of the product. Used on the login brand panel. */

const HEX_ANGLES = [30, 90, 150, 210, 270, 330];

function hexPoints(cx: number, cy: number, r: number): string {
  return HEX_ANGLES.map((a) => {
    const rad = (Math.PI * a) / 180;
    return `${(cx + r * Math.cos(rad)).toFixed(1)},${(cy + r * Math.sin(rad)).toFixed(1)}`;
  }).join(" ");
}

interface Satellite {
  cx: number;
  cy: number;
  label: string;
  labelX: number;
  labelY: number;
  anchor: "start" | "middle";
  icon: React.ReactNode;
  line?: [number, number, number, number];
}

const ICON = {
  stroke: "#e2e8f0",
  strokeWidth: 1.8,
  fill: "none",
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function iconAt(cx: number, cy: number, children: React.ReactNode) {
  return <g transform={`translate(${cx - 12} ${cy - 12})`} {...ICON}>{children}</g>;
}

const SATELLITES: Satellite[] = [
  {
    cx: 360, cy: 72, label: "Knowledge", labelX: 404, labelY: 77, anchor: "start",
    line: [360, 108, 360, 124],
    icon: (
      <>
        <path d="M4 5c3-1.5 6-1.5 8 0v14c-2-1.5-5-1.5-8 0z" />
        <path d="M20 5c-3-1.5-6-1.5-8 0v14c2-1.5 5-1.5 8 0z" />
      </>
    ),
  },
  {
    cx: 148, cy: 175, label: "Memory", labelX: 148, labelY: 232, anchor: "middle",
    line: [176, 196, 254, 240],
    icon: (
      <>
        <ellipse cx="12" cy="6" rx="8" ry="3" />
        <path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
        <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
      </>
    ),
  },
  {
    cx: 132, cy: 368, label: "Search", labelX: 132, labelY: 425, anchor: "middle",
    line: [163, 352, 230, 320],
    icon: (
      <>
        <circle cx="11" cy="11" r="6" />
        <path d="M15.5 15.5 20 20" />
      </>
    ),
  },
  {
    cx: 572, cy: 175, label: "Agents", labelX: 572, labelY: 232, anchor: "middle",
    line: [544, 196, 466, 240],
    icon: (
      <>
        <rect x="5" y="8" width="14" height="11" rx="3" />
        <path d="M12 8V4" />
        <circle cx="12" cy="3" r="1" />
        <circle cx="9.5" cy="13" r="1.2" fill="#e2e8f0" stroke="none" />
        <circle cx="14.5" cy="13" r="1.2" fill="#e2e8f0" stroke="none" />
      </>
    ),
  },
  {
    cx: 588, cy: 368, label: "APIs", labelX: 588, labelY: 425, anchor: "middle",
    line: [558, 352, 490, 320],
    icon: (
      <>
        <path d="M9 7l-5 5 5 5" />
        <path d="M15 7l5 5-5 5" />
      </>
    ),
  },
  {
    cx: 360, cy: 502, label: "Governance", labelX: 404, labelY: 507, anchor: "start",
    icon: (
      <>
        <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
        <path d="M9 11.5l2 2 4-4" />
      </>
    ),
  },
];

export function BrandHero({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 720 600" className={className} role="img" aria-label="EKC platform">
      <defs>
        <radialGradient id="bh-bg" cx="50%" cy="42%" r="75%">
          <stop offset="0%" stopColor="#16233f" />
          <stop offset="60%" stopColor="#0b1428" />
          <stop offset="100%" stopColor="#060b16" />
        </radialGradient>
        <linearGradient id="bh-top" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#93c5fd" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
        <linearGradient id="bh-left" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e3a8a" />
          <stop offset="100%" stopColor="#16255c" />
        </linearGradient>
        <linearGradient id="bh-right" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#1e40af" />
        </linearGradient>
        <linearGradient id="bh-mini" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#0891b2" />
        </linearGradient>
        <filter id="bh-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="5" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="bh-soft" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="12" />
        </filter>
        <pattern id="bh-dots" width="26" height="26" patternUnits="userSpaceOnUse">
          <circle cx="1.5" cy="1.5" r="1.5" fill="#3b82f6" opacity="0.08" />
        </pattern>
      </defs>

      <rect width="720" height="600" rx="24" fill="url(#bh-bg)" />
      <rect width="720" height="600" rx="24" fill="url(#bh-dots)" />

      {/* ground glow */}
      <ellipse cx="360" cy="482" rx="130" ry="16" fill="#3b82f6" opacity="0.28" filter="url(#bh-soft)" />

      {/* connectors */}
      {SATELLITES.filter((s) => s.line).map((s) => {
        const [x1, y1, x2, y2] = s.line as [number, number, number, number];
        return (
          <g key={s.label}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#60a5fa" strokeWidth="1.4" opacity="0.35" />
            <circle cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} r="2.2" fill="#7dd3fc" filter="url(#bh-glow)" />
          </g>
        );
      })}

      {/* the cube */}
      <g>
        <polygon points="235,262 360,334 360,464 235,392" fill="url(#bh-left)" />
        <polygon points="360,334 485,262 485,392 360,464" fill="url(#bh-right)" />
        <polygon points="360,190 485,262 360,334 235,262" fill="url(#bh-top)" />
        {/* luminous edges */}
        <g fill="none" stroke="#93c5fd" strokeWidth="2" strokeLinejoin="round" filter="url(#bh-glow)" opacity="0.9">
          <polygon points="360,190 485,262 360,334 235,262" />
          <path d="M235 262v130l125 72 125-72V262" />
          <path d="M360 334v130" />
        </g>
        {/* people glyph on the left face (iso-sheared) */}
        <g transform="matrix(0.862 0.497 0 1 268 258)" opacity="0.85">
          <circle cx="26" cy="26" r="9" fill="#93c5fd" />
          <path d="M8 62c0-10 8-18 18-18s18 8 18 18" fill="#93c5fd" />
        </g>
        {/* EKC on the right face (iso-sheared) */}
        <text
          transform="matrix(0.862 -0.497 0 1 424 388)"
          textAnchor="middle"
          fontFamily="var(--font-geist-sans), 'Segoe UI', sans-serif"
          fontSize="40"
          fontWeight="800"
          letterSpacing="3"
          fill="#ffffff"
          filter="url(#bh-glow)"
        >
          EKC
        </text>
      </g>

      {/* floating core */}
      <g filter="url(#bh-glow)">
        <polygon points="360,128 386,142 360,156 334,142" fill="url(#bh-mini)" />
        <polygon points="334,142 360,156 360,182 334,168" fill="#0e7490" />
        <polygon points="360,156 386,142 386,168 360,182" fill="#0891b2" />
      </g>

      {/* satellites */}
      {SATELLITES.map((s) => (
        <g key={s.label}>
          <polygon
            points={hexPoints(s.cx, s.cy, 34)}
            fill="#0d1830"
            fillOpacity="0.92"
            stroke="#3b82f6"
            strokeWidth="1.6"
            strokeLinejoin="round"
            filter="url(#bh-glow)"
          />
          {iconAt(s.cx, s.cy, s.icon)}
          <text
            x={s.labelX}
            y={s.labelY}
            textAnchor={s.anchor}
            fontFamily="var(--font-geist-sans), 'Segoe UI', sans-serif"
            fontSize="14"
            fontWeight="500"
            fill="#cbd5e1"
          >
            {s.label}
          </text>
        </g>
      ))}

      {/* wordmark */}
      <text
        x="360"
        y="576"
        textAnchor="middle"
        fontFamily="var(--font-geist-sans), 'Segoe UI', sans-serif"
        fontSize="13"
        fontWeight="600"
        letterSpacing="6"
      >
        <tspan fill="#67e8f9">ENTERPRISE </tspan>
        <tspan fill="#cbd5e1">KNOWLEDGE COPILOT</tspan>
      </text>
    </svg>
  );
}
