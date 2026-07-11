"use client";

/** Integrations: folder-sync connector, webhooks, automation endpoints. */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  createWebhook,
  deleteWebhook,
  listWebhooks,
  syncFolder,
} from "@/lib/api";
import type { FolderSyncReport, WebhookRead } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Callout, Card, Pill, Spinner } from "@/components/ui";

const EVENTS = [
  "query.refused",
  "query.needs_review",
  "review.resolved",
  "document.ingested",
  "document.failed",
] as const;

function FolderSync() {
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<FolderSyncReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await syncFolder(path.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-5 px-5 py-4">
      <h2 className="text-[15px] font-semibold">Folder connector</h2>
      <p className="mt-1 mb-3 max-w-[620px] text-[12.5px] text-ink-2">
        Ingest every new file from a folder on the server — a mounted network share, a synced
        bucket, or a drop folder. Files are deduplicated by content, so re-syncing is safe;
        schedule it with cron to keep the corpus current.
      </p>
      <form onSubmit={run} className="flex flex-wrap items-center gap-2.5">
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="D:\\shares\\contracts   or   /mnt/policies"
          required
          className="min-w-[300px] flex-1 rounded-lg border border-line-strong bg-canvas px-3 py-2 font-mono text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
        />
        <Button variant="primary" type="submit" disabled={busy || !path.trim()}>
          {busy ? "Syncing…" : "Sync now"}
        </Button>
      </form>
      {error && (
        <div className="mt-3">
          <Callout tone="warn" icon="⚠">
            {error}
          </Callout>
        </div>
      )}
      {report && (
        <div className="mt-3 rounded-lg border border-line bg-subtle px-4 py-3 text-[12.5px]">
          <p>
            Scanned <b>{report.scanned}</b> · ingested <b>{report.ingested.length}</b> · already
            known <b>{report.skipped_existing}</b> · unsupported{" "}
            <b>{report.skipped_unsupported}</b> · failed <b>{report.failed.length}</b>
          </p>
          {report.ingested.length > 0 && (
            <p className="mt-1 font-mono text-[11.5px] text-ink-2">
              + {report.ingested.join(", ")}
            </p>
          )}
          {report.failed.map((f) => (
            <p key={f.filename} className="mt-1 font-mono text-[11.5px] text-danger">
              ✕ {f.filename}: {f.error}
            </p>
          ))}
        </div>
      )}
    </Card>
  );
}

function Webhooks() {
  const [hooks, setHooks] = useState<WebhookRead[] | null>(null);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [selected, setSelected] = useState<string[]>(["query.refused", "query.needs_review"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listWebhooks()
      .then(setHooks)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not reach the server."),
      );
  }, []);

  useEffect(refresh, [refresh]);

  function toggle(event: string) {
    setSelected((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  }

  async function create(formEvent: FormEvent) {
    formEvent.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createWebhook(url.trim(), selected, secret.trim() || null);
      setUrl("");
      setSecret("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the webhook.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(hook: WebhookRead) {
    if (!window.confirm(`Delete the webhook for ${hook.url}?`)) return;
    try {
      await deleteWebhook(hook.id);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the webhook.");
    }
  }

  return (
    <Card className="mb-5 px-5 py-4">
      <h2 className="text-[15px] font-semibold">Webhooks</h2>
      <p className="mt-1 mb-3 max-w-[620px] text-[12.5px] text-ink-2">
        Push trust events into your own systems — open a ticket on every refusal, ping a channel
        when an answer needs review. Deliveries are HMAC-SHA256 signed when a secret is set
        (header <code className="font-mono text-[11px]">X-EKC-Signature</code>).
      </p>

      <form onSubmit={create} className="flex flex-col gap-2.5">
        <div className="flex flex-wrap gap-2.5">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://hooks.yourcompany.com/ekc"
            required
            type="url"
            className="min-w-[280px] flex-1 rounded-lg border border-line-strong bg-canvas px-3 py-2 font-mono text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <input
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="signing secret (min 16 chars, recommended)"
            minLength={16}
            className="min-w-[240px] rounded-lg border border-line-strong bg-canvas px-3 py-2 font-mono text-[12.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {EVENTS.map((event) => (
            <button
              key={event}
              type="button"
              onClick={() => toggle(event)}
              className={`rounded-full border px-3 py-1 font-mono text-[11px] transition-colors ${
                selected.includes(event)
                  ? "border-accent bg-accent-subtle text-accent"
                  : "border-line text-ink-2 hover:border-line-strong"
              }`}
            >
              {event}
            </button>
          ))}
          <span className="ml-auto">
            <Button variant="primary" type="submit" disabled={busy || !url.trim() || !selected.length}>
              Add webhook
            </Button>
          </span>
        </div>
      </form>

      {error && (
        <div className="mt-3">
          <Callout tone="warn" icon="⚠">
            {error}
          </Callout>
        </div>
      )}

      <div className="mt-4">
        {hooks === null ? (
          <Spinner />
        ) : hooks.length === 0 ? (
          <p className="text-[12.5px] text-ink-3">No webhooks yet.</p>
        ) : (
          hooks.map((hook) => (
            <div
              key={hook.id}
              className="group flex flex-wrap items-center gap-2.5 border-t border-line py-2.5 first:border-t-0"
            >
              <code className="font-mono text-xs font-semibold">{hook.url}</code>
              {hook.events.map((e) => (
                <Pill key={e} tone="accent">
                  {e}
                </Pill>
              ))}
              {hook.has_secret && <Pill tone="ok">signed</Pill>}
              <span className="ml-auto opacity-0 transition-opacity group-hover:opacity-100">
                <Button variant="ghost" small className="text-danger" onClick={() => void remove(hook)}>
                  Delete
                </Button>
              </span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

function AutomationNotes() {
  return (
    <Card className="px-5 py-4">
      <h2 className="text-[15px] font-semibold">Automation endpoints</h2>
      <div className="mt-2 flex flex-col gap-3 text-[12.5px] text-ink-2">
        <div>
          <p className="font-semibold text-ink">Batch queries — for pipelines and back-office jobs</p>
          <code className="mt-1 block overflow-x-auto rounded-lg bg-subtle px-3 py-2 font-mono text-[11.5px]">
            POST /api/v1/query/batch {"{"} &quot;queries&quot;: [&quot;…&quot;, &quot;…&quot;] {"}"} · X-API-Key: ekc_…
          </code>
        </div>
        <div>
          <p className="font-semibold text-ink">MCP — connect Claude and other AI agents</p>
          <code className="mt-1 block overflow-x-auto rounded-lg bg-subtle px-3 py-2 font-mono text-[11.5px]">
            {"{"} &quot;command&quot;: &quot;ekc-mcp&quot;, &quot;env&quot;: {"{"} &quot;EKC_URL&quot;: &quot;…&quot;, &quot;EKC_API_KEY&quot;: &quot;ekc_…&quot; {"}"} {"}"}
          </code>
          <p className="mt-1">
            9 tools including grounded ask/search and the <b>setup-copilot</b> interview prompt.
          </p>
        </div>
        <p>
          Full interactive API reference at{" "}
          <a href="/docs" className="text-accent hover:underline">
            /docs
          </a>
          .
        </p>
      </div>
    </Card>
  );
}

export default function IntegrationsPage() {
  return (
    <div>
      <PageHead
        title="Integrations"
        desc="Feed the knowledge base automatically, push trust events into your workflows, and plug in your own systems and AI agents."
      />
      <FolderSync />
      <Webhooks />
      <AutomationNotes />
    </div>
  );
}
