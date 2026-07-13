/** Brand mark: a chip holding a brain, radiating to knowledge nodes.
 *  Pure SVG on design tokens — crisp at any size, follows the theme.
 *  Brain paths from lucide (ISC). Mirrored in app/icon.svg (favicon). */

const BRAIN_PATHS = [
  "M12 18V5",
  "M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4",
  "M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5",
  "M17.997 5.125a4 4 0 0 1 2.526 5.77",
  "M18 18a4 4 0 0 0 2-7.464",
  "M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517",
  "M6 18a4 4 0 0 1-2-7.464",
  "M6.003 5.125a4 4 0 0 0-2.526 5.77",
];

export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden className="shrink-0">
      {/* spokes */}
      <g stroke="var(--accent)" strokeWidth="1.9" strokeLinecap="round">
        <line x1="24" y1="11" x2="24" y2="5.5" />
        <line x1="24" y1="37" x2="24" y2="42.5" />
        <line x1="11" y1="24" x2="5.5" y2="24" />
        <line x1="37" y1="24" x2="42.5" y2="24" />
        <line x1="14" y1="14" x2="9.8" y2="9.8" />
        <line x1="34" y1="34" x2="38.2" y2="38.2" />
        <line x1="34" y1="14" x2="38.2" y2="9.8" />
        <line x1="14" y1="34" x2="9.8" y2="38.2" />
      </g>
      {/* nodes — mixed weights and tints, like a live graph */}
      <circle cx="24" cy="4.6" r="2.5" fill="var(--accent)" />
      <circle cx="24" cy="43.4" r="2.5" fill="var(--accent)" />
      <circle cx="4.6" cy="24" r="2.5" fill="var(--accent-border)" />
      <circle cx="43.4" cy="24" r="2.2" fill="none" stroke="var(--accent)" strokeWidth="1.7" />
      <circle cx="8.4" cy="8.4" r="2" fill="var(--accent-border)" />
      <circle cx="39.6" cy="39.6" r="2.3" fill="var(--accent)" />
      <circle cx="39.6" cy="8.4" r="1.9" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
      <circle cx="8.4" cy="39.6" r="1.9" fill="var(--accent)" />
      {/* chip */}
      <rect x="11.5" y="11.5" width="25" height="25" rx="7" fill="var(--accent)" />
      {/* brain */}
      <g
        transform="translate(15.1 15.1) scale(0.74)"
        fill="none"
        stroke="#fff"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {BRAIN_PATHS.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
    </svg>
  );
}
