/** Small presentational kit — tokens from the approved design (Mockup C). */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

type Tone = "ok" | "warn" | "danger" | "accent" | "gray";

const PILL_TONES: Record<Tone, string> = {
  ok: "bg-ok-subtle text-ok",
  warn: "bg-warn-subtle text-warn",
  danger: "bg-danger-subtle text-danger",
  accent: "bg-accent-subtle text-accent",
  gray: "bg-subtle text-ink-2",
};

export function Pill({
  tone,
  dot = false,
  children,
}: {
  tone: Tone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-px text-xs font-medium whitespace-nowrap ${PILL_TONES[tone]}`}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover border-transparent",
  secondary: "bg-canvas text-ink border-line-strong hover:bg-subtle shadow-sm",
  danger: "bg-canvas text-danger border-line-strong hover:bg-danger-subtle hover:border-danger shadow-sm",
  ghost: "text-ink-2 border-transparent hover:bg-subtle hover:text-ink",
};

export function Button({
  variant = "secondary",
  small = false,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  small?: boolean;
}) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 rounded-lg border font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-45 ${
        small ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-[13.5px]"
      } ${BUTTON_VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`rounded-xl border border-line bg-canvas shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function Callout({
  tone,
  icon,
  children,
}: {
  tone: "warn" | "danger";
  icon: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-[13.5px] leading-relaxed ${
        tone === "danger" ? "bg-danger-subtle" : "bg-warn-subtle"
      }`}
    >
      <span aria-hidden>{icon}</span>
      <span>{children}</span>
    </div>
  );
}

export function Meter({ name, value, tone = "ok" }: { name: string; value: number; tone?: Tone }) {
  const color =
    tone === "warn" ? "bg-warn" : tone === "danger" ? "bg-danger" : tone === "accent" ? "bg-accent" : "bg-ok";
  return (
    <div className="flex items-center gap-2.5 text-xs text-ink-2">
      <span className="w-25 shrink-0">{name}</span>
      <span className="h-[5px] flex-1 overflow-hidden rounded-sm bg-subtle">
        <span
          className={`block h-full rounded-sm ${color}`}
          style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }}
        />
      </span>
      <span className="w-9 shrink-0 text-right font-mono text-[11.5px] font-semibold text-ink">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

export function Cite({ marker, onClick }: { marker: number; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="mx-0.5 inline-flex h-[19px] min-w-[19px] translate-y-[-2px] items-center justify-center rounded-[5px] bg-accent-subtle px-1 font-mono text-[11px] font-semibold text-accent transition-colors hover:bg-accent hover:text-white"
    >
      {marker}
    </button>
  );
}

export function Field({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-semibold">{label}</span>
      <input
        className="w-full rounded-lg border border-line-strong bg-canvas px-3 py-2 text-[13.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-subtle)] focus:outline-none"
        {...props}
      />
    </label>
  );
}

export function Spinner() {
  return (
    <span
      aria-label="Loading"
      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-accent"
    />
  );
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="py-14 text-center">
      <p className="text-[15px] font-semibold">{title}</p>
      <p className="mt-1 text-[13px] text-ink-2">{hint}</p>
    </div>
  );
}
