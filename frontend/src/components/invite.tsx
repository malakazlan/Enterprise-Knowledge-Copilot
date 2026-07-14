"use client";

/** Invite a teammate: creates the account with a generated temporary password
 *  the admin hands over out-of-band. Members can also arrive via SSO. */

import { UserPlus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError, register } from "@/lib/api";
import type { UserRead } from "@/lib/types";
import { Button, Field } from "@/components/ui";

const ALPHABET = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789";

function tempPassword(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(14));
  return Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join("");
}

export default function InviteMemberModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated?: (user: UserRead) => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password] = useState(tempPassword);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<UserRead | null>(null);
  const [copied, setCopied] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const user = await register(email.trim(), password, name.trim());
      setCreated(user);
      onCreated?.(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4"
      onClick={onClose}
    >
      <div
        className="w-[440px] max-w-full rounded-xl border border-line bg-canvas shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-3.5">
          <UserPlus size={15} className="text-accent" />
          <span className="text-[14px] font-semibold">Invite a team member</span>
          <button onClick={onClose} className="ml-auto text-ink-3 hover:text-ink" title="Close">
            <X size={15} />
          </button>
        </div>

        {created ? (
          <div className="px-5 py-4">
            <p className="text-[13.5px]">
              <b>{created.email}</b> can sign in now. Share these credentials over a secure
              channel — the password is shown only here.
            </p>
            <div className="mt-3 rounded-lg border border-line bg-subtle p-3 font-mono text-[12.5px]">
              <p className="truncate">email: {created.email}</p>
              <p className="mt-1 truncate">password: {password}</p>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <Button
                onClick={() => {
                  void navigator.clipboard.writeText(
                    `Knowledge Copilot access\nemail: ${created.email}\npassword: ${password}`,
                  );
                  setCopied(true);
                }}
              >
                {copied ? "Copied" : "Copy credentials"}
              </Button>
              <Button variant="ghost" onClick={onClose}>
                Done
              </Button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3 px-5 py-4">
            <Field
              label="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Rivera"
              required
            />
            <Field
              label="Work email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@company.com"
              required
            />
            <p className="text-[12px] text-ink-2">
              A temporary password is generated for you and revealed after the account is
              created. New members join with the <b>member</b> role.
            </p>
            {error && <p className="text-[12.5px] text-danger">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={busy || !email.trim()}>
                {busy ? "Creating…" : "Create account"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
