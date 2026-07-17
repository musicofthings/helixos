"use client";

import { FormEvent, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Copy, Link2, LoaderCircle, Trash2, Users, X } from "lucide-react";
import type { Workspace, WorkspaceInvite, WorkspaceShareRole } from "@helixos/types";

import {
  useCreateWorkspaceInvite,
  useCreateWorkspaceShare,
  useRevokeWorkspaceInvite,
  useRevokeWorkspaceShare,
  useUpdateWorkspaceShare,
  useWorkspaceCollaboration
} from "../../hooks/use-helix-api";
import { getApiBaseUrl } from "../../lib/api-config";

type ShareTab = "collaborators" | "invite";

function inviteIsActive(invite: WorkspaceInvite): boolean {
  if (invite.revoked_at) return false;
  if (invite.max_uses != null && invite.accepted_count >= invite.max_uses) return false;
  return new Date(invite.expires_at) > new Date();
}

export function ShareWorkspaceModal({
  workspace,
  organizationId,
  onClose,
  onActivity
}: {
  workspace: Workspace;
  organizationId?: string;
  onClose: () => void;
  onActivity: (message: string) => void;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [tab, setTab] = useState<ShareTab>("collaborators");
  const collaboration = useWorkspaceCollaboration(workspace.id, true);
  const createShare = useCreateWorkspaceShare(organizationId);
  const updateShare = useUpdateWorkspaceShare(organizationId);
  const revokeShare = useRevokeWorkspaceShare(organizationId);
  const createInvite = useCreateWorkspaceInvite(organizationId);
  const revokeInvite = useRevokeWorkspaceInvite(organizationId);

  const [subject, setSubject] = useState("");
  const [shareRole, setShareRole] = useState<WorkspaceShareRole>("viewer");
  const [inviteRole, setInviteRole] = useState<WorkspaceShareRole>("viewer");
  const [createdTokens, setCreatedTokens] = useState<Record<string, string>>({});
  const [copiedInviteId, setCopiedInviteId] = useState<string | null>(null);

  const shares = collaboration.data?.shares ?? [];
  const invites = collaboration.data?.invites ?? [];
  const activeInvites = invites.filter(inviteIsActive);
  const inactiveInvites = invites.filter((invite) => !inviteIsActive(invite));

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Tab" || !dialog) return;
      const focusable = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    dialog.addEventListener("keydown", onKeyDown);
    return () => dialog.removeEventListener("keydown", onKeyDown);
  }, []);

  function submitShare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!subject.trim()) return;
    createShare.mutate(
      { workspaceId: workspace.id, subject: subject.trim(), role: shareRole },
      {
        onSuccess: (share) => {
          onActivity(`Granted ${share.role} access to ${share.subject}`);
          setSubject("");
        },
        onError: (error) =>
          onActivity(error instanceof Error ? error.message : "Failed to add collaborator")
      }
    );
  }

  function createInviteLink() {
    createInvite.mutate(
      { workspaceId: workspace.id, role: inviteRole, expiresInHours: 168 },
      {
        onSuccess: (invite) => {
          if (invite.token) {
            setCreatedTokens((current) => ({ ...current, [invite.id]: invite.token! }));
          }
          onActivity(`Created invite link (${invite.role})`);
          setTab("invite");
        },
        onError: (error) =>
          onActivity(error instanceof Error ? error.message : "Failed to create invite")
      }
    );
  }

  function inviteAcceptUrl(token: string) {
    return `${getApiBaseUrl().replace(/\/$/, "")}/api/v1/workspace-invites/${token}/accept`;
  }

  async function copyInviteUrl(inviteId: string, token: string) {
    const url = inviteAcceptUrl(token);
    try {
      await navigator.clipboard.writeText(url);
      setCopiedInviteId(inviteId);
      onActivity("Invite URL copied");
      window.setTimeout(
        () => setCopiedInviteId((current) => (current === inviteId ? null : current)),
        2000
      );
    } catch {
      onActivity("Could not copy invite URL");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-lg rounded-md border border-black/10 bg-white shadow-lg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-black/10 px-4 py-3">
          <div>
            <h2 id={titleId} className="text-sm font-semibold text-ink">
              Share workspace
            </h2>
            <p className="mt-0.5 text-xs text-graphite">{workspace.name}</p>
            <p className="mt-1 text-[11px] text-graphite">
              Org members keep full access. Grants and invites add collaborators (viewer / editor).
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-graphite hover:bg-black/5"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex gap-1 border-b border-black/10 px-4 pt-2">
          <TabButton active={tab === "collaborators"} onClick={() => setTab("collaborators")} icon={Users}>
            Collaborators
          </TabButton>
          <TabButton active={tab === "invite"} onClick={() => setTab("invite")} icon={Link2}>
            Invite link
          </TabButton>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-4">
          {collaboration.isLoading ? (
            <p className="inline-flex items-center gap-2 text-xs text-graphite">
              <LoaderCircle size={14} className="animate-spin" /> Loading collaboration…
            </p>
          ) : tab === "collaborators" ? (
            <div className="grid gap-4">
              <form onSubmit={submitShare} className="grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3">
                <label className="text-[11px] font-medium uppercase tracking-wide text-graphite">
                  Subject
                </label>
                <input
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="user_demo_admin or name@lab.example"
                  className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                />
                <label className="text-[11px] font-medium uppercase tracking-wide text-graphite">Role</label>
                <select
                  value={shareRole}
                  onChange={(event) => setShareRole(event.target.value as WorkspaceShareRole)}
                  className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                <button
                  type="submit"
                  disabled={createShare.isPending || !subject.trim()}
                  className="mt-1 inline-flex justify-center rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {createShare.isPending ? "Adding…" : "Add collaborator"}
                </button>
              </form>

              {shares.length === 0 ? (
                <p className="text-sm text-graphite">No collaborators yet.</p>
              ) : (
                <ul className="grid gap-2">
                  {shares.map((share) => (
                    <li
                      key={share.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-black/10 px-3 py-2"
                    >
                      <div>
                        <div className="text-sm font-medium text-ink">{share.subject}</div>
                        <div className="text-[11px] text-graphite capitalize">{share.role}</div>
                      </div>
                      <div className="flex items-center gap-1">
                        <select
                          value={share.role}
                          aria-label={`Role for ${share.subject}`}
                          onChange={(event) =>
                            updateShare.mutate(
                              {
                                workspaceId: workspace.id,
                                shareId: share.id,
                                role: event.target.value as WorkspaceShareRole
                              },
                              {
                                onSuccess: (updated) =>
                                  onActivity(`Updated ${updated.subject} to ${updated.role}`),
                                onError: (error) =>
                                  onActivity(
                                    error instanceof Error ? error.message : "Failed to update role"
                                  )
                              }
                            )
                          }
                          disabled={updateShare.isPending}
                          className="rounded-md border border-black/10 bg-white px-2 py-1 text-[11px] outline-none focus:border-fern"
                        >
                          <option value="viewer">Viewer</option>
                          <option value="editor">Editor</option>
                        </select>
                        <button
                          type="button"
                          onClick={() =>
                            revokeShare.mutate(
                              { workspaceId: workspace.id, shareId: share.id },
                              {
                                onSuccess: () => onActivity(`Revoked access for ${share.subject}`),
                                onError: (error) =>
                                  onActivity(
                                    error instanceof Error ? error.message : "Failed to revoke share"
                                  )
                              }
                            )
                          }
                          disabled={revokeShare.isPending}
                          className="rounded-md p-1.5 text-graphite hover:bg-red-50 hover:text-red-700"
                          aria-label={`Revoke ${share.subject}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="grid gap-4">
              <div className="grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3">
                <label className="text-[11px] font-medium uppercase tracking-wide text-graphite">
                  Invite role
                </label>
                <select
                  value={inviteRole}
                  onChange={(event) => setInviteRole(event.target.value as WorkspaceShareRole)}
                  className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                >
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
                <button
                  type="button"
                  onClick={createInviteLink}
                  disabled={createInvite.isPending}
                  className="mt-1 inline-flex justify-center rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {createInvite.isPending ? "Creating…" : "Create invite link"}
                </button>
                <p className="text-[11px] text-graphite">
                  The accept URL is shown once after create. Copy it before closing this dialog.
                </p>
              </div>

              {activeInvites.length === 0 && inactiveInvites.length === 0 ? (
                <p className="text-sm text-graphite">No invite links yet.</p>
              ) : null}

              {activeInvites.length > 0 ? (
                <InviteSection title="Active">
                  {activeInvites.map((invite) => {
                    const token = createdTokens[invite.id];
                    return (
                      <li key={invite.id} className="grid gap-2 rounded-md border border-black/10 px-3 py-2">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-sm font-medium capitalize text-ink">
                              {invite.role} · Active
                            </div>
                            <div className="mt-0.5 text-[11px] text-graphite">
                              Expires {new Date(invite.expires_at).toLocaleString()}
                              {invite.max_uses != null ? ` · Max ${invite.max_uses} uses` : ""}
                              {invite.accepted_count > 0
                                ? ` · Accepted ${invite.accepted_count}×`
                                : ""}
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              revokeInvite.mutate(
                                { workspaceId: workspace.id, inviteId: invite.id },
                                {
                                  onSuccess: () => {
                                    setCreatedTokens((current) => {
                                      const next = { ...current };
                                      delete next[invite.id];
                                      return next;
                                    });
                                    onActivity("Invite revoked");
                                  },
                                  onError: (error) =>
                                    onActivity(
                                      error instanceof Error
                                        ? error.message
                                        : "Failed to revoke invite"
                                    )
                                }
                              )
                            }
                            disabled={revokeInvite.isPending}
                            className="rounded-md p-1.5 text-graphite hover:bg-red-50 hover:text-red-700"
                            aria-label="Revoke invite"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        {token ? (
                          <div className="flex items-center gap-2">
                            <code className="flex-1 truncate rounded bg-[#eef1ed] px-2 py-1 text-[11px] text-ink">
                              {inviteAcceptUrl(token)}
                            </code>
                            <button
                              type="button"
                              onClick={() => void copyInviteUrl(invite.id, token)}
                              className="inline-flex items-center gap-1 rounded-md border border-black/10 px-2 py-1 text-[11px] font-medium hover:bg-black/5"
                            >
                              <Copy size={12} />
                              {copiedInviteId === invite.id ? "Copied" : "Copy"}
                            </button>
                          </div>
                        ) : (
                          <p className="text-[11px] text-graphite">
                            Token hidden after create. Revoke and create a new link to share again.
                          </p>
                        )}
                      </li>
                    );
                  })}
                </InviteSection>
              ) : null}

              {inactiveInvites.length > 0 ? (
                <InviteSection title="Inactive">
                  {inactiveInvites.map((invite) => (
                    <li key={invite.id} className="rounded-md border border-black/10 px-3 py-2">
                      <div className="text-sm font-medium capitalize text-ink">
                        {invite.role} · Inactive
                      </div>
                      <div className="mt-0.5 text-[11px] text-graphite">
                        {invite.revoked_at
                          ? `Revoked ${new Date(invite.revoked_at).toLocaleString()}`
                          : `Expired ${new Date(invite.expires_at).toLocaleString()}`}
                        {invite.accepted_count > 0
                          ? ` · Accepted ${invite.accepted_count}×`
                          : ""}
                      </div>
                    </li>
                  ))}
                </InviteSection>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InviteSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid gap-2">
      <h3 className="text-[11px] font-medium uppercase tracking-wide text-graphite">{title}</h3>
      <ul className="grid gap-2">{children}</ul>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Users;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium ${
        active ? "border-fern text-ink" : "border-transparent text-graphite hover:text-ink"
      }`}
    >
      <Icon size={14} />
      {children}
    </button>
  );
}
