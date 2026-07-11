"use client";

/** API keys: create (secret shown once), list, revoke. */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, createApiKey, listApiKeys, revokeApiKey } from "@/lib/api";
import type { ApiKeyCreated, ApiKeyRead } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Callout, Card, EmptyState, Pill, Spinner } from "@/components/ui";

export default function KeysPage() {
  const [keys, setKeys] = useState<ApiKeyRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState("user");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  const refresh = useCallback(() => {
    listApiKeys()
      .then(setKeys)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not reach the server."),
      );
  }, []);

  useEffect(refresh, [refresh]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCreated(await createApiKey(name.trim(), role));
      setName("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the key.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(key: ApiKeyRead) {
    if (!window.confirm(`Revoke “${key.name}”? Clients using it stop working immediately.`))
      return;
    try {
      await revokeApiKey(key.id);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not revoke the key.");
    }
  }

  return (
    <div>
      <PageHead
        title="API keys"
        desc="Machine access for your own applications — send the key as an X-API-Key header. Secrets are stored hashed and shown exactly once."
      />

      <Card className="mb-5 px-5 py-4">
        <form onSubmit={create} className="flex flex-wrap items-end gap-3">
          <label className="min-w-[220px] flex-1">
            <span className="mb-1.5 block text-[12.5px] font-semibold">Key name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="intranet-search"
              required
              className="w-full rounded-lg border border-line-strong bg-canvas px-3 py-2 text-[13.5px] shadow-sm placeholder:text-ink-3 focus:border-accent focus:outline-none"
            />
          </label>
          <label>
            <span className="mb-1.5 block text-[12.5px] font-semibold">Role</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-lg border border-line-strong bg-canvas px-3 py-2 text-[13.5px] shadow-sm focus:border-accent focus:outline-none"
            >
              <option value="user">user — query & search</option>
              <option value="reviewer">reviewer — + review queue</option>
              <option value="admin">admin — full access</option>
            </select>
          </label>
          <Button variant="primary" type="submit" disabled={busy || !name.trim()}>
            Create key
          </Button>
        </form>

        {created && (
          <div className="mt-4 rounded-lg border border-accent-border bg-accent-subtle px-4 py-3">
            <p className="text-[12.5px] font-semibold">
              Copy this key now — it will not be shown again.
            </p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 overflow-x-auto rounded-md bg-canvas px-3 py-2 font-mono text-xs">
                {created.key}
              </code>
              <Button
                small
                onClick={() => {
                  void navigator.clipboard.writeText(created.key);
                }}
              >
                Copy
              </Button>
              <Button small variant="ghost" onClick={() => setCreated(null)}>
                Done
              </Button>
            </div>
          </div>
        )}
      </Card>

      {error && (
        <div className="mb-4">
          <Callout tone="warn" icon="⚠">
            {error}
          </Callout>
        </div>
      )}

      <Card className="overflow-hidden">
        {keys === null ? (
          <div className="flex justify-center py-14">
            <Spinner />
          </div>
        ) : keys.length === 0 ? (
          <EmptyState title="No API keys yet" hint="Create one above to integrate your own apps." />
        ) : (
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="bg-subtle text-left text-xs font-semibold text-ink-2">
                <th className="px-4 py-2.5">Name</th>
                <th className="px-4 py-2.5">Prefix</th>
                <th className="px-4 py-2.5">Role</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Last used</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="group border-t border-line hover:bg-subtle">
                  <td className="px-4 py-3 font-semibold">{key.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">{key.key_prefix}…</td>
                  <td className="px-4 py-3">
                    <Pill tone="gray">{key.role}</Pill>
                  </td>
                  <td className="px-4 py-3">
                    {key.revoked_at ? (
                      <Pill tone="danger" dot>
                        Revoked
                      </Pill>
                    ) : (
                      <Pill tone="ok" dot>
                        Active
                      </Pill>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">
                    {key.last_used_at
                      ? new Date(key.last_used_at).toLocaleString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "never"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {!key.revoked_at && (
                      <span className="opacity-0 transition-opacity group-hover:opacity-100">
                        <Button
                          variant="ghost"
                          small
                          className="text-danger"
                          onClick={() => void revoke(key)}
                        >
                          Revoke
                        </Button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
