"use client";

/** Ask: grounded Q&A with inline citations, confidence, and sources. */

import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, listProfiles, runQuery } from "@/lib/api";
import type { QueryResponse } from "@/lib/types";
import { Button, Callout, Card, Cite, Meter, Spinner } from "@/components/ui";

interface Exchange {
  question: string;
  response: QueryResponse | null;
  error: string | null;
}

/** Render answer text with [n] markers as citation chips. */
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

function ConfidencePill({ response }: { response: QueryResponse }) {
  const [open, setOpen] = useState(false);
  const value = response.confidence;
  const tone =
    value >= 0.8
      ? "bg-ok-subtle text-ok"
      : value >= 0.5
        ? "bg-warn-subtle text-warn"
        : "bg-danger-subtle text-danger";
  const label = value >= 0.8 ? "High" : value >= 0.5 ? "Medium" : "Low";
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12.5px] font-semibold ${tone}`}
      >
        <span className="h-[7px] w-[7px] rounded-full bg-current" />
        {label} confidence · {value.toFixed(2)} {open ? "▴" : "▾"}
      </button>
      {open && (
        <Card className="mt-3 flex max-w-[420px] flex-col gap-2 px-4 py-3.5">
          {Object.entries(response.confidence_breakdown).map(([name, v]) => (
            <Meter key={name} name={name} value={v} tone={v >= 0.8 ? "ok" : "warn"} />
          ))}
          {response.needs_review && (
            <p className="mt-1 text-xs text-warn">Flagged for human review.</p>
          )}
        </Card>
      )}
    </div>
  );
}

function BotAnswer({ response }: { response: QueryResponse }) {
  return (
    <div className="mb-8">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-[7px] bg-accent text-xs font-bold text-white">
          K
        </span>
        <span className="text-[13px] font-semibold">Copilot</span>
        <span className="text-xs text-ink-3">
          · {response.profile} · {Math.round(response.took_ms)} ms
        </span>
      </div>

      {response.answered && response.answer ? (
        <>
          <p className="max-w-[680px] text-[14.5px] leading-[1.7]">
            <AnswerText text={response.answer} />
          </p>
          <div className="mt-3.5 flex flex-wrap items-center gap-3.5">
            <ConfidencePill response={response} />
            <Button variant="ghost" small onClick={() => navigator.clipboard.writeText(response.answer ?? "")}>
              Copy
            </Button>
          </div>
          {response.citations.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2.5">
              {response.citations.map((c) => (
                <Link
                  key={c.marker}
                  href={`/viewer/?doc=${c.document_id}&chunk=${c.chunk_id}`}
                  className="flex min-w-[200px] max-w-[260px] flex-col gap-1 rounded-lg border border-line bg-canvas px-3 py-2.5 shadow-sm transition-shadow hover:border-accent-border hover:shadow-md"
                >
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="grid h-[17px] min-w-[17px] place-items-center rounded-[5px] bg-accent-subtle font-mono text-[10px] font-bold text-accent">
                      {c.marker}
                    </span>
                    <span className="truncate font-mono text-[11px] font-semibold">{c.filename}</span>
                    {c.page_number != null && (
                      <span className="ml-auto text-[11px] text-ink-3">p.{c.page_number}</span>
                    )}
                  </div>
                  <p className="line-clamp-2 text-[11.5px] leading-normal text-ink-2">
                    “{c.snippet}”
                  </p>
                </Link>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="max-w-[640px]">
          <Callout tone="danger" icon="✕">
            <b>Declined.</b> The corpus does not support an answer to this question
            {response.refusal_reason && (
              <>
                {" "}
                (<code className="font-mono text-xs">{response.refusal_reason}</code>)
              </>
            )}
            . Confidence {response.confidence.toFixed(2)} — no answer is safer than a wrong one.
          </Callout>
        </div>
      )}
    </div>
  );
}

export default function AskPage() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [question, setQuestion] = useState("");
  const [profiles, setProfiles] = useState<string[]>([]);
  const [profile, setProfile] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listProfiles()
      .then((list) => setProfiles(list.map((p) => p.name)))
      .catch(() => setProfiles([]));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchanges]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setExchanges((prev) => [...prev, { question: q, response: null, error: null }]);
    try {
      const response = await runQuery(q, profile);
      setExchanges((prev) =>
        prev.map((e, i) => (i === prev.length - 1 ? { ...e, response } : e)),
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not reach the server.";
      setExchanges((prev) =>
        prev.map((e, i) => (i === prev.length - 1 ? { ...e, error: message } : e)),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-[780px]">
      {exchanges.length === 0 && (
        <div className="pt-24 pb-16 text-center">
          <h1 className="text-[26px] font-bold tracking-[-0.02em]">Ask your documents</h1>
          <p className="mt-2 text-sm text-ink-2">
            Every answer cites its sources and carries a confidence score. When the evidence
            isn’t there, it declines.
          </p>
        </div>
      )}

      {exchanges.map((exchange, i) => (
        <div key={i}>
          <div className="mb-5 flex justify-end">
            <p className="max-w-[75%] rounded-[14px_14px_4px_14px] bg-subtle px-4 py-2.5 text-sm">
              {exchange.question}
            </p>
          </div>
          {exchange.response && <BotAnswer response={exchange.response} />}
          {exchange.error && (
            <div className="mb-8 max-w-[640px]">
              <Callout tone="warn" icon="⚠">
                {exchange.error}
              </Callout>
            </div>
          )}
          {!exchange.response && !exchange.error && (
            <div className="mb-8 flex items-center gap-2.5 text-sm text-ink-3">
              <Spinner /> Searching the corpus…
            </div>
          )}
        </div>
      ))}
      <div ref={endRef} />

      <form
        onSubmit={submit}
        className="sticky bottom-6 mt-9 flex items-center gap-2.5 rounded-[14px] border border-line-strong bg-canvas py-2.5 pr-2.5 pl-4 shadow-lg"
      >
        {profiles.length > 0 && (
          <select
            value={profile ?? ""}
            onChange={(e) => setProfile(e.target.value || null)}
            className="shrink-0 rounded-full bg-subtle px-3 py-1 text-xs font-medium text-ink-2 focus:outline-none"
          >
            <option value="">default profile</option>
            {profiles.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything — answers cite their sources…"
          className="min-w-0 flex-1 bg-transparent text-sm placeholder:text-ink-3 focus:outline-none"
        />
        <Button variant="primary" type="submit" disabled={busy || !question.trim()}>
          Ask
        </Button>
      </form>
    </div>
  );
}
