"use client";

/** Insights: deployment statistics for admins. */

import { useEffect, useState } from "react";

import { adminStats, ApiError } from "@/lib/api";
import type { AdminStats } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Callout, Card, Spinner } from "@/components/ui";

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "warn";
}) {
  return (
    <Card className="px-4.5 py-4">
      <p className="text-xs font-medium text-ink-2">{label}</p>
      <p
        className={`mt-1 text-[26px] leading-tight font-bold tracking-[-0.02em] ${
          tone === "warn" ? "text-warn" : ""
        }`}
      >
        {value}
      </p>
      {sub && <p className="mt-1 text-[11.5px] text-ink-3">{sub}</p>}
    </Card>
  );
}

export default function InsightsPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminStats()
      .then(setStats)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setError("Insights require the admin role.");
        } else {
          setError(err instanceof ApiError ? err.message : "Could not reach the server.");
        }
      });
  }, []);

  if (error) {
    return (
      <div>
        <PageHead title="Insights" />
        <Callout tone="warn" icon="⚠">
          {error}
        </Callout>
      </div>
    );
  }

  if (!stats) {
    return (
      <div>
        <PageHead title="Insights" />
        <div className="flex justify-center py-14">
          <Spinner />
        </div>
      </div>
    );
  }

  const answerRate =
    stats.queries_total > 0 ? Math.round((stats.queries_answered / stats.queries_total) * 100) : 0;
  const refusals = Object.entries(stats.refusal_breakdown).sort((a, b) => b[1] - a[1]);
  const refusalMax = Math.max(1, ...refusals.map(([, n]) => n));

  return (
    <div>
      <PageHead title="Insights" desc="How this deployment is performing." />

      <div className="mb-3.5 grid grid-cols-4 gap-3.5 max-md:grid-cols-2">
        <Stat
          label="Documents"
          value={String(stats.documents_total)}
          sub={`${stats.chunks_total} chunks${stats.documents_failed ? ` · ${stats.documents_failed} failed` : ""}${stats.documents_stale ? ` · ${stats.documents_stale} stale` : ""}`}
          tone={stats.documents_stale > 0 ? "warn" : undefined}
        />
        <Stat
          label="Queries"
          value={String(stats.queries_total)}
          sub={`${stats.queries_answered} answered · ${stats.queries_refused} declined`}
        />
        <Stat
          label="Answer rate"
          value={`${answerRate}%`}
          sub={
            stats.avg_confidence_answered != null
              ? `avg confidence ${stats.avg_confidence_answered.toFixed(2)}`
              : undefined
          }
        />
        <Stat
          label="Pending reviews"
          value={String(stats.reviews_pending)}
          sub={`${stats.api_keys_active} API keys · ${stats.users_total} users`}
          tone={stats.reviews_pending > 0 ? "warn" : undefined}
        />
      </div>

      <Card className="px-5.5 py-4.5">
        <h2 className="mb-4 text-[13.5px] font-semibold">Why answers were declined</h2>
        {refusals.length === 0 ? (
          <p className="text-[13px] text-ink-2">No refusals recorded yet.</p>
        ) : (
          refusals.map(([reason, count]) => (
            <div key={reason} className="mb-3 grid grid-cols-[180px_1fr_36px] items-center gap-3 last:mb-0">
              <span className="truncate font-mono text-[11px] text-ink-2">{reason}</span>
              <span className="h-2 overflow-hidden rounded bg-subtle">
                <span
                  className={`block h-full rounded ${reason === "insufficient_evidence" ? "bg-danger" : "bg-warn"}`}
                  style={{ width: `${Math.round((count / refusalMax) * 100)}%` }}
                />
              </span>
              <span className="text-right font-mono text-[11.5px] font-semibold">{count}</span>
            </div>
          ))
        )}
        <p className="mt-3.5 text-[11.5px] text-ink-3">
          Declining is a feature — every refusal is logged with its reason.
        </p>
      </Card>
    </div>
  );
}
