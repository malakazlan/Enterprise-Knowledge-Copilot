"use client";

/** Review queue: approve or reject answers flagged by the confidence policy. */

import { Fragment, useCallback, useEffect, useState } from "react";

import { ApiError, listReviews, resolveReview } from "@/lib/api";
import type { ReviewItem } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Callout, Card, Cite, EmptyState, TableSkeleton } from "@/components/ui";

function AnswerText({ text }: { text: string }) {
  const parts = text.split(/\[(\d{1,2})\]/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <Cite key={i} marker={Number(part)} /> : <Fragment key={i}>{part}</Fragment>,
      )}
    </>
  );
}

function ReviewCard({
  item,
  onResolved,
}: {
  item: ReviewItem;
  onResolved: (id: string) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resolve(action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await resolveReview(item.id, action, note.trim());
      onResolved(item.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resolve.");
      setBusy(false);
    }
  }

  return (
    <Card className="mb-3.5 px-5.5 py-5">
      <div className="mb-2.5 flex items-baseline gap-3">
        <h2 className="flex-1 text-[15.5px] font-semibold tracking-[-0.01em]">{item.query}</h2>
        <span className="shrink-0 text-xs text-ink-3">
          {new Date(item.created_at).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
      {item.answer && (
        <p className="mb-3 max-w-[640px] text-[13.5px] leading-relaxed text-ink-2">
          <AnswerText text={item.answer} />
        </p>
      )}
      <Callout tone="warn" icon="⚑">
        confidence <code className="font-mono text-xs">{item.confidence.toFixed(2)}</code> below the
        review threshold · profile <code className="font-mono text-xs">{item.profile}</code> ·
        grounded <code className="font-mono text-xs">{item.grounded_ratio.toFixed(2)}</code>
      </Callout>
      {error && <p className="mt-2 text-[12.5px] text-danger">{error}</p>}
      <div className="mt-3.5 flex items-center gap-2">
        <Button variant="primary" small disabled={busy} onClick={() => void resolve("approve")}>
          Approve
        </Button>
        <Button variant="danger" small disabled={busy} onClick={() => void resolve("reject")}>
          Reject
        </Button>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note for the record (optional)…"
          className="max-w-[360px] flex-1 rounded-lg border border-line-strong bg-canvas px-3 py-1 text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
        />
      </div>
    </Card>
  );
}

export default function ReviewPage() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listReviews("pending")
      .then(setItems)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setError("Review access requires the reviewer or admin role.");
        } else {
          setError(err instanceof ApiError ? err.message : "Could not reach the server.");
        }
      });
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <div>
      <PageHead
        title="Review queue"
        desc="Answers the confidence policy flagged for human judgment. Every resolution is recorded — who, when, verdict, note."
      />

      {error && (
        <Callout tone="warn" icon="⚠">
          {error}
        </Callout>
      )}

      {!error &&
        (items === null ? (
          <Card>
            <TableSkeleton rows={3} />
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <EmptyState
              title="Queue is clear"
              hint="Nothing awaits review — flagged answers will appear here."
            />
          </Card>
        ) : (
          items.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              onResolved={(id) => setItems((prev) => prev?.filter((i) => i.id !== id) ?? null)}
            />
          ))
        ))}
    </div>
  );
}
