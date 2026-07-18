/** Brand mark: stacked knowledge sheets with a folded corner — the "Knowledge
 *  Stack". Pure SVG, cyan-to-blue brand gradient (fixed, not theme tokens, so
 *  the identity stays constant in light and dark). Mirrored in app/icon.svg. */

export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden className="shrink-0">
      <defs>
        <linearGradient id="lm-top" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#5eead4" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
        <linearGradient id="lm-mid" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#2563eb" />
        </linearGradient>
        <linearGradient id="lm-bot" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#1e3a8a" />
        </linearGradient>
      </defs>
      <rect x="16" y="30" width="34" height="24" rx="7" fill="url(#lm-bot)" />
      <rect x="13" y="20" width="34" height="24" rx="7" fill="url(#lm-mid)" />
      <path
        d="M17 10 h20 l10 10 v6 a7 7 0 0 1 -7 7 H17 a7 7 0 0 1 -7 -7 v-9 a7 7 0 0 1 7 -7 z"
        fill="url(#lm-top)"
      />
      <path d="M37 10 l10 10 h-7 a3 3 0 0 1 -3 -3 z" fill="#0e7490" opacity="0.55" />
    </svg>
  );
}
