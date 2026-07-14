"use client";

/** Team — workspace members. Listing is admin-only on the API; everyone else
 *  gets a graceful explanation instead of a broken table. */

import { UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ApiError, listUsers } from "@/lib/api";
import type { UserRead } from "@/lib/types";
import { PageHead } from "@/components/shell";
import { Button, Card, EmptyState, Pill, TableSkeleton } from "@/components/ui";
import InviteMemberModal from "@/components/invite";

const ROLE_TONES = { admin: "accent", reviewer: "warn", user: "gray" } as const;

export default function TeamPage() {
  const [users, setUsers] = useState<UserRead[] | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);

  const refresh = useCallback(() => {
    listUsers()
      .then((list) => {
        setUsers(list);
        setForbidden(false);
      })
      .catch((err: unknown) => {
        setUsers([]);
        setForbidden(err instanceof ApiError && err.status === 403);
      });
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHead
          title="Team"
          desc="Everyone with access to this workspace. Answers, reviews, and knowledge writes are attributed to the member who made them."
        />
        {!forbidden && users !== null && (
          <Button variant="primary" onClick={() => setInviteOpen(true)}>
            <UserPlus size={14} /> Invite member
          </Button>
        )}
      </div>

      <Card className="overflow-hidden">
        {users === null ? (
          <TableSkeleton rows={4} />
        ) : forbidden ? (
          <EmptyState
            title="The member roster is admin-only"
            hint="Ask a workspace administrator to add or manage accounts."
          />
        ) : users.length === 0 ? (
          <EmptyState title="No members found" hint="Invite your first teammate to get started." />
        ) : (
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="bg-subtle text-left text-xs font-semibold text-ink-2">
                <th className="px-4 py-2.5">Member</th>
                <th className="px-4 py-2.5">Role</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-t border-line hover:bg-subtle">
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-3">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-line-strong bg-hover text-[11px] font-semibold text-ink-2">
                        {(user.full_name ?? user.email).slice(0, 2).toUpperCase()}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold">
                          {user.full_name ?? "—"}
                        </span>
                        <span className="block truncate text-xs text-ink-3">{user.email}</span>
                      </span>
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Pill tone={ROLE_TONES[user.role]}>{user.role}</Pill>
                  </td>
                  <td className="px-4 py-3">
                    {user.is_active ? (
                      <Pill tone="ok" dot>
                        Active
                      </Pill>
                    ) : (
                      <Pill tone="danger" dot>
                        Disabled
                      </Pill>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-2">
                    {new Date(user.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {inviteOpen && (
        <InviteMemberModal onClose={() => setInviteOpen(false)} onCreated={refresh} />
      )}
    </>
  );
}
