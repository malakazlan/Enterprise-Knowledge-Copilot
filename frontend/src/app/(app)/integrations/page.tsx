"use client";

/** Integrations: folder-sync connector, webhooks, automation endpoints. */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  connectorAuthorizeUrl,
  createConnector,
  createWebhook,
  deleteConnector,
  deleteWebhook,
  getAccessToken,
  listCollections,
  listConnectors,
  listWebhooks,
  syncConnector,
} from "@/lib/api";
import type { CollectionRead, ConnectorRead, WebhookRead } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Callout, Card, Pill, Spinner } from "@/components/ui";

const EVENTS = [
  "query.refused",
  "query.needs_review",
  "review.resolved",
  "document.ingested",
  "document.failed",
] as const;

function relSync(iso: string | null): string {
  if (!iso) return "never synced";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `synced ${mins}m ago`;
  if (mins < 1440) return `synced ${Math.round(mins / 60)}h ago`;
  return `synced ${Math.round(mins / 1440)}d ago`;
}

const BRAND_MARKS: Record<string, React.ReactNode> = {
  gdrive: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <path d="M8.6 2.5h6.8l6.3 11h-6.8z" fill="#FFBA00" />
      <path d="M15.4 13.5h6.3l-3.4 6h-6.3z" fill="#2684FC" />
      <path d="M8.6 2.5 2.3 13.5l3.4 6 6.3-11z" fill="#00AC47" />
    </svg>
  ),
  folder: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <path
        d="M3 5.5A1.5 1.5 0 0 1 4.5 4h5l2 2.5h8A1.5 1.5 0 0 1 21 8v10a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18z"
        fill="#64748B"
      />
    </svg>
  ),
  slack: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <rect x="9.5" y="2" width="3.4" height="8" rx="1.7" fill="#36C5F0" />
      <rect x="14" y="9.5" width="8" height="3.4" rx="1.7" fill="#2EB67D" />
      <rect x="11" y="14" width="3.4" height="8" rx="1.7" fill="#ECB22E" />
      <rect x="2" y="11" width="8" height="3.4" rx="1.7" fill="#E01E5A" />
    </svg>
  ),
  gmail: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <path d="M3 6.5v11h3.5v-7L12 14l5.5-3.5v7H21v-11L12 12z" fill="#EA4335" />
      <path d="M3 6.5 12 12l9-5.5V6a1.5 1.5 0 0 0-2.3-1.3L12 8.9 5.3 4.7A1.5 1.5 0 0 0 3 6z" fill="#C5221F" opacity=".85" />
    </svg>
  ),
  dropbox: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden fill="#0061FF">
      <path d="m12 6.9-4.5 2.9L12 12.7l-4.5 2.9L3 12.6l4.5-2.8L3 6.9l4.5-2.9zm0 0 4.5-2.9L21 6.9l-4.5 2.9L21 12.6l-4.5 3L12 12.7l4.5-2.9zM7.5 17.6l4.5-2.9 4.5 2.9L12 20.5z" />
    </svg>
  ),
  sharepoint: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <circle cx="10" cy="8" r="6" fill="#036C70" />
      <circle cx="16" cy="13" r="5" fill="#1A9BA1" />
      <circle cx="10.5" cy="17" r="4.5" fill="#37C6D0" />
    </svg>
  ),
  notion: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="3" fill="#fff" stroke="#111" strokeWidth="1.4" />
      <path d="M8 17V8.5l1.8-.2 4.6 6.8V8h1.8v9l-1.9.2-4.6-6.8V17z" fill="#111" />
    </svg>
  ),
  confluence: (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <path d="M4 17.5c2.6-4.3 5-5.4 9.3-3.3l5 2.4-2 4.1-4.8-2.3c-2.3-1.1-3.2-.8-4.7 1.4z" fill="#2684FF" />
      <path d="M20 6.5c-2.6 4.3-5 5.4-9.3 3.3l-5-2.4 2-4.1 4.8 2.3c2.3 1.1 3.2.8 4.7-1.4z" fill="#0052CC" />
    </svg>
  ),
};

const PROVIDERS: {
  key: string;
  label: string;
  blurb: string;
  status: "live" | "oauth" | "soon";
}[] = [
  { key: "gdrive", label: "Google Drive", blurb: "Docs, Sheets, Slides & files — one click", status: "oauth" },
  { key: "folder", label: "Server folder", blurb: "Mounted shares, drop folders, rclone", status: "live" },
  { key: "slack", label: "Slack", blurb: "Channels & threads as knowledge", status: "soon" },
  { key: "notion", label: "Notion", blurb: "Pages and databases", status: "soon" },
  { key: "gmail", label: "Gmail", blurb: "Label-scoped mail ingestion", status: "soon" },
  { key: "dropbox", label: "Dropbox", blurb: "Team folders", status: "soon" },
  { key: "sharepoint", label: "SharePoint", blurb: "Sites & document libraries", status: "soon" },
  { key: "confluence", label: "Confluence", blurb: "Spaces and pages", status: "soon" },
];

function Connectors() {
  const [connectors, setConnectors] = useState<ConnectorRead[] | null>(null);
  const [collections, setCollections] = useState<CollectionRead[]>([]);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [collectionId, setCollectionId] = useState("");
  const [syncing, setSyncing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listConnectors()
      .then(setConnectors)
      .catch((err) => {
        setConnectors([]);
        if (err instanceof ApiError && err.status === 403) {
          setError("This section requires the admin role — sign in as an administrator.");
        } else {
          setError(err instanceof ApiError ? err.message : "Could not reach the server.");
        }
      });
    listCollections()
      .then(setCollections)
      .catch(() => setCollections([]));
  }, []);

  useEffect(refresh, [refresh]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createConnector(name.trim(), "folder", {
        path: path.trim(),
        recursive: true,
        ...(collectionId ? { collection_id: collectionId } : {}),
      });
      setName("");
      setPath("");
      setCollectionId("");
      setAdding(false);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the connector.");
    }
  }

  async function connectDrive() {
    const name = window.prompt("Name this Google Drive connector:", "company-drive");
    if (!name) return;
    setError(null);
    try {
      const connector = await createConnector(name.trim(), "gdrive", {});
      const token = getAccessToken();
      const res = await fetch(connectorAuthorizeUrl(connector.id), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        redirect: "manual",
      });
      const target = res.headers.get("location");
      if (target) window.location.href = target;
      else setError("Google Drive is not configured on the server (GDRIVE_CLIENT_ID…).");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the Google connect flow.");
    }
  }

  async function runSync(id: string) {
    setSyncing(id);
    setError(null);
    try {
      await syncConnector(id);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setSyncing(null);
    }
  }

  async function remove(connector: ConnectorRead) {
    if (!window.confirm(`Delete connector “${connector.name}”? Documents stay.`)) return;
    await deleteConnector(connector.id).catch(() => undefined);
    refresh();
  }

  return (
    <Card className="mb-5 px-5 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[15px] font-semibold">Connectors</h2>
        <p className="text-[12.5px] text-ink-2">
          Connect a source once; sync on demand or on a schedule. Re-syncs are idempotent.
        </p>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2.5 max-md:grid-cols-2">
        {PROVIDERS.map((provider) => (
          <button
            key={provider.key}
            disabled={provider.status === "soon"}
            onClick={() => {
              if (provider.key === "folder") setAdding((v) => !v);
              else if (provider.key === "gdrive") void connectDrive();
            }}
            className={`group flex items-start gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-all ${
              provider.status === "soon"
                ? "border-line opacity-55"
                : "border-line-strong bg-canvas shadow-sm hover:border-accent hover:shadow-md"
            }`}
          >
            <span className="mt-0.5 shrink-0">{BRAND_MARKS[provider.key]}</span>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-[13px] font-semibold">
                {provider.label}
                {provider.status !== "soon" ? (
                  <Pill tone="ok">live</Pill>
                ) : (
                  <span className="text-[10px] text-ink-3">soon</span>
                )}
              </span>
              <span className="block truncate text-[11px] text-ink-3">{provider.blurb}</span>
            </span>
            {provider.status !== "soon" && (
              <span className="ml-auto text-ink-3 group-hover:text-accent">+</span>
            )}
          </button>
        ))}
      </div>

      {adding && (
        <form
          onSubmit={create}
          className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-line bg-subtle px-3 py-2.5"
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="name, e.g. hq-share"
            required
            className="w-[160px] rounded-lg border border-line-strong bg-canvas px-3 py-1.5 text-[12.5px] placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="server path, e.g. /mnt/policies"
            required
            className="min-w-[220px] flex-1 rounded-lg border border-line-strong bg-canvas px-3 py-1.5 font-mono text-[12px] placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          {collections.length > 0 && (
            <select
              value={collectionId}
              onChange={(e) => setCollectionId(e.target.value)}
              className="rounded-lg border border-line-strong bg-canvas px-2.5 py-1.5 text-[12.5px] text-ink-2 focus:outline-none"
            >
              <option value="">into: shared</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  into: {c.name}
                </option>
              ))}
            </select>
          )}
          <Button variant="primary" small type="submit" disabled={!name.trim() || !path.trim()}>
            Save
          </Button>
        </form>
      )}

      {error && (
        <div className="mt-3">
          <Callout tone="warn" icon="⚠">
            {error}
          </Callout>
        </div>
      )}

      <div className="mt-3">
        {connectors === null ? (
          <Spinner />
        ) : connectors.length === 0 ? (
          !error && <p className="text-[12.5px] text-ink-3">No connectors yet.</p>
        ) : (
          connectors.map((connector) => (
            <div
              key={connector.id}
              className="group flex flex-wrap items-center gap-2.5 border-t border-line py-2.5 first:border-t-0"
            >
              <span className="text-[13px] font-semibold">{connector.name}</span>
              <Pill tone="gray">{connector.type}</Pill>
              <code className="font-mono text-[11px] text-ink-2">
                {String(connector.config["path"] ?? "")}
              </code>
              <span className="text-[11.5px] text-ink-3">{relSync(connector.last_sync_at)}</span>
              {connector.last_sync_report && (
                <span className="text-[11.5px] text-ink-3">
                  · +{connector.last_sync_report.ingested.length} new,{" "}
                  {connector.last_sync_report.skipped_existing} known
                  {connector.last_sync_report.failed.length > 0 &&
                    `, ${connector.last_sync_report.failed.length} failed`}
                </span>
              )}
              <span className="ml-auto flex items-center gap-1">
                <Button
                  small
                  disabled={syncing === connector.id}
                  onClick={() => void runSync(connector.id)}
                >
                  {syncing === connector.id ? "Syncing…" : "Sync now"}
                </Button>
                <Button
                  variant="ghost"
                  small
                  className="text-danger opacity-0 group-hover:opacity-100"
                  onClick={() => void remove(connector)}
                >
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
      .catch((err) => {
        setHooks([]);
        if (err instanceof ApiError && err.status === 403) {
          setError("This section requires the admin role — sign in as an administrator.");
        } else {
          setError(err instanceof ApiError ? err.message : "Could not reach the server.");
        }
      });
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
          !error && <p className="text-[12.5px] text-ink-3">No webhooks yet.</p>
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
          <p className="font-semibold text-ink">Context packs — token-budgeted context for agent prompts</p>
          <code className="mt-1 block overflow-x-auto rounded-lg bg-subtle px-3 py-2 font-mono text-[11.5px]">
            POST /api/v1/context {"{"} &quot;task&quot;: &quot;…&quot;, &quot;max_tokens&quot;: 2000 {"}"}
          </code>
        </div>
        <div>
          <p className="font-semibold text-ink">Knowledge write-back — agents deposit what they learn</p>
          <code className="mt-1 block overflow-x-auto rounded-lg bg-subtle px-3 py-2 font-mono text-[11.5px]">
            POST /api/v1/knowledge {"{"} &quot;title&quot;: &quot;…&quot;, &quot;content&quot;: &quot;…&quot;, &quot;verify_in_days&quot;: 90 {"}"}
          </code>
          <p className="mt-1">Requires a reviewer- or admin-role key; entries are retrievable within seconds.</p>
        </div>
        <div>
          <p className="font-semibold text-ink">MCP — connect Claude and other AI agents</p>
          <code className="mt-1 block overflow-x-auto rounded-lg bg-subtle px-3 py-2 font-mono text-[11.5px]">
            {"{"} &quot;command&quot;: &quot;ekc-mcp&quot;, &quot;env&quot;: {"{"} &quot;EKC_URL&quot;: &quot;…&quot;, &quot;EKC_API_KEY&quot;: &quot;ekc_…&quot; {"}"} {"}"}
          </code>
          <p className="mt-1">
            11 tools including grounded ask/search, context packs, knowledge write-back, and the <b>setup-copilot</b> interview prompt.
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
      <Connectors />
      <Webhooks />
      <AutomationNotes />
    </div>
  );
}
