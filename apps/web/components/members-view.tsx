"use client";

import type { OrgRole } from "@helixos/types";
import { FormEvent, useState } from "react";

import {
  useAddOrgMember,
  useChangeMemberRole,
  useOrgMembers,
  useRemoveOrgMember,
  useRevokeMemberInvite
} from "../hooks/use-helix-api";
import { errorMessage } from "../lib/error-message";
import { ORG_ROLES, roleLabel } from "../lib/org-roles";

interface MembersViewProps {
  organizationId?: string;
  /** The signed-in user's role in this organization; only admins get controls. */
  role?: OrgRole | null;
  apiEnabled: boolean;
  onActivity: (message: string) => void;
}

export function MembersView({ organizationId, role, apiEnabled, onActivity }: MembersViewProps) {
  const canManage = role === "admin";
  const members = useOrgMembers(organizationId, apiEnabled);
  const add = useAddOrgMember(organizationId);
  const changeRole = useChangeMemberRole(organizationId);
  const remove = useRemoveOrgMember(organizationId);
  const revoke = useRevokeMemberInvite(organizationId);

  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<OrgRole>("scientist");
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  const error = add.error ?? changeRole.error ?? remove.error ?? revoke.error ?? members.error;

  function submit(event: FormEvent) {
    event.preventDefault();
    const address = email.trim();
    if (!address) return;
    add.mutate(
      { email: address, role: newRole },
      {
        onSuccess: (result) => {
          setEmail("");
          onActivity(result.member ? `Added ${address} as ${roleLabel(newRole)}` : `Invited ${address}`);
        }
      }
    );
  }

  return (
    <section aria-labelledby="members-title" className="mt-6 grid max-w-3xl gap-6">
      <div>
        <h2 id="members-title" className="text-lg font-semibold text-ink">
          Members
        </h2>
        <p className="mt-1 text-sm text-graphite">
          {canManage
            ? "Invite people by email. They join with the role you pick when they first sign in."
            : "Only organization admins can change membership."}
        </p>
      </div>

      {error ? (
        <p role="alert" className="rounded-md border border-signal/30 bg-[#eef6f7] px-3 py-2 text-xs text-signal">
          {errorMessage(error, "Request failed")}
        </p>
      ) : null}

      {canManage ? (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-md border border-black/10 bg-white p-3">
          <label className="grid gap-1 text-xs text-graphite">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="colleague@lab.org"
              className="w-64 rounded-md border border-black/10 px-2 py-1.5 text-sm text-ink outline-none focus:border-fern"
            />
          </label>
          <label className="grid gap-1 text-xs text-graphite">
            Role
            <select
              value={newRole}
              onChange={(event) => setNewRole(event.target.value as OrgRole)}
              className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm text-ink outline-none focus:border-fern"
            >
              {ORG_ROLES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={add.isPending}
            className="rounded-md bg-fern px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {add.isPending ? "Adding…" : "Add member"}
          </button>
        </form>
      ) : null}

      <div className="overflow-hidden rounded-md border border-black/10 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#f1f4ef] text-xs uppercase tracking-wide text-graphite">
            <tr>
              <th className="px-3 py-2 font-semibold">Person</th>
              <th className="px-3 py-2 font-semibold">Role</th>
              {canManage ? <th className="px-3 py-2" /> : null}
            </tr>
          </thead>
          <tbody>
            {members.isLoading ? (
              <tr>
                <td className="px-3 py-3 text-graphite" colSpan={3}>
                  Loading members…
                </td>
              </tr>
            ) : null}
            {members.data?.members.map((member) => (
              <tr key={member.user_id} className="border-t border-black/5">
                <td className="px-3 py-2">
                  <div className="font-medium text-ink">{member.display_name ?? member.email ?? member.user_id}</div>
                  {member.display_name && member.email ? (
                    <div className="text-xs text-graphite">{member.email}</div>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  {canManage ? (
                    <select
                      aria-label={`Role for ${member.email ?? member.user_id}`}
                      value={member.role}
                      disabled={changeRole.isPending}
                      onChange={(event) =>
                        changeRole.mutate({ userId: member.user_id, role: event.target.value as OrgRole })
                      }
                      className="rounded-md border border-black/10 bg-white px-2 py-1 text-xs text-ink"
                    >
                      {ORG_ROLES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    roleLabel(member.role)
                  )}
                </td>
                {canManage ? (
                  <td className="px-3 py-2 text-right">
                    {confirmRemove === member.user_id ? (
                      <button
                        type="button"
                        onClick={() => {
                          setConfirmRemove(null);
                          remove.mutate(member.user_id, {
                            onSuccess: () => onActivity(`Removed ${member.email ?? member.user_id}`)
                          });
                        }}
                        className="rounded-md bg-red-600 px-2 py-1 text-xs font-medium text-white"
                      >
                        Confirm remove
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmRemove(member.user_id)}
                        className="text-xs text-graphite underline hover:text-ink"
                      >
                        Remove
                      </button>
                    )}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {members.data && members.data.invites.length > 0 ? (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-graphite">Pending invites</h3>
          <ul className="grid gap-2">
            {members.data.invites.map((invite) => (
              <li
                key={invite.id}
                className="flex items-center justify-between gap-3 rounded-md border border-black/10 bg-white px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-medium text-ink">{invite.email}</span>
                  <span className="ml-2 text-xs text-graphite">{roleLabel(invite.role)}</span>
                </span>
                {canManage ? (
                  <button
                    type="button"
                    onClick={() =>
                      revoke.mutate(invite.id, { onSuccess: () => onActivity(`Revoked invite for ${invite.email}`) })
                    }
                    className="text-xs text-graphite underline hover:text-ink"
                  >
                    Revoke
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
