import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HelixOSApiError } from "@helixos/api-client";
import type { Workspace, WorkspaceInvite, WorkspaceShare } from "@helixos/types";

import { api, makeQueryClient, resetApi, wrapperFor } from "./helpers";

vi.mock("../lib/api-config", () => ({
  createHelixClient: () => api,
  getApiBaseUrl: () => "http://api.test"
}));

import { ShareWorkspaceModal } from "../components/eln/share-workspace-modal";

const workspace = {
  id: "ws_1", organization_id: "org_qc", name: "QC lab", category: "custom", subcategory: null,
  description: null, is_default: false, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z"
} as Workspace;

const share = (id: string, subject: string, role: "viewer" | "editor"): WorkspaceShare => ({
  id, workspace_id: "ws_1", organization_id: "org_qc", subject, role, granted_by: "owner", created_at: "2026-01-01T00:00:00Z"
});

const invite = (over: Partial<WorkspaceInvite>): WorkspaceInvite => ({
  id: "inv_1", workspace_id: "ws_1", organization_id: "org_qc", token: null, role: "viewer", created_by: "owner",
  expires_at: "2999-01-01T00:00:00Z", revoked_at: null, accepted_count: 0, max_uses: null,
  created_at: "2026-01-01T00:00:00Z", ...over
});

function renderModalWith(collaboration: { shares: WorkspaceShare[]; invites: WorkspaceInvite[] }) {
  api.listWorkspaceCollaboration.mockResolvedValue(collaboration);
  const onActivity = vi.fn();
  const onClose = vi.fn();
  const queryClient = makeQueryClient();
  render(
    <ShareWorkspaceModal workspace={workspace} organizationId="org_qc" onClose={onClose} onActivity={onActivity} />,
    { wrapper: wrapperFor(queryClient) }
  );
  return { onActivity, onClose, queryClient };
}

const renderModal = renderModalWith;

beforeEach(() => resetApi());
afterEach(() => cleanup());

describe("ShareWorkspaceModal collaborator roles", () => {
  it("lists each collaborator with their current role", async () => {
    renderModal({ shares: [share("s1", "ana@lab.example", "editor"), share("s2", "bo@lab.example", "viewer")], invites: [] });

    const anaRole = (await screen.findByLabelText("Role for ana@lab.example")) as HTMLSelectElement;
    expect(anaRole.value).toBe("editor");
    expect((screen.getByLabelText("Role for bo@lab.example") as HTMLSelectElement).value).toBe("viewer");
  });

  it("changes a role through the API and reports it", async () => {
    api.updateWorkspaceShare.mockResolvedValue(share("s2", "bo@lab.example", "editor"));
    const { onActivity } = renderModal({ shares: [share("s2", "bo@lab.example", "viewer")], invites: [] });

    fireEvent.change(await screen.findByLabelText("Role for bo@lab.example"), { target: { value: "editor" } });

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("Updated bo@lab.example to editor"));
    expect(api.updateWorkspaceShare).toHaveBeenCalledWith("ws_1", "s2", { role: "editor" });
  });

  it("shows the server's refusal, including the request ref, when a role change fails", async () => {
    api.updateWorkspaceShare.mockRejectedValue(
      new HelixOSApiError(403, "forbidden", "Only owners can change roles", {}, "req_denied")
    );
    const { onActivity } = renderModal({ shares: [share("s2", "bo@lab.example", "viewer")], invites: [] });

    fireEvent.change(await screen.findByLabelText("Role for bo@lab.example"), { target: { value: "editor" } });

    await waitFor(() =>
      expect(onActivity).toHaveBeenCalledWith("Only owners can change roles (ref req_denied)")
    );
  });

  it("adds a collaborator with the chosen role and clears the form", async () => {
    api.createWorkspaceShare.mockResolvedValue(share("s9", "new@lab.example", "editor"));
    const { onActivity } = renderModal({ shares: [], invites: [] });

    fireEvent.change(await screen.findByPlaceholderText(/name@lab.example/), { target: { value: "  new@lab.example " } });
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "editor" } });
    fireEvent.click(screen.getByRole("button", { name: "Add collaborator" }));

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("Granted editor access to new@lab.example"));
    expect(api.createWorkspaceShare).toHaveBeenCalledWith("ws_1", { subject: "new@lab.example", role: "editor" });
    await waitFor(() => expect((screen.getByPlaceholderText(/name@lab.example/) as HTMLInputElement).value).toBe(""));
  });

  it("keeps the typed subject when adding fails, and reports why", async () => {
    api.createWorkspaceShare.mockRejectedValue(
      new HelixOSApiError(422, "invalid_subject", "Share subject must be a known user id or an email address", {}, "req_422")
    );
    const { onActivity } = renderModal({ shares: [], invites: [] });

    fireEvent.change(await screen.findByPlaceholderText(/name@lab.example/), { target: { value: "nobody" } });
    fireEvent.click(screen.getByRole("button", { name: "Add collaborator" }));

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith(expect.stringContaining("(ref req_422)")));
    expect((screen.getByPlaceholderText(/name@lab.example/) as HTMLInputElement).value).toBe("nobody");
  });

  it("revokes access and reports a failure without removing the row", async () => {
    api.revokeWorkspaceShare.mockRejectedValue(new Error("network down"));
    const { onActivity } = renderModal({ shares: [share("s2", "bo@lab.example", "viewer")], invites: [] });

    fireEvent.click(await screen.findByLabelText("Revoke bo@lab.example"));

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("network down"));
    expect(screen.getByText("bo@lab.example")).toBeTruthy();
  });
});

describe("ShareWorkspaceModal invites", () => {
  async function openInviteTab() {
    fireEvent.click(await screen.findByRole("button", { name: /Invite link/ }));
  }

  it("separates active invites from revoked, exhausted and expired ones", async () => {
    renderModal({
      shares: [],
      invites: [
        invite({ id: "active", role: "editor" }),
        invite({ id: "revoked", revoked_at: "2026-01-02T00:00:00Z" }),
        invite({ id: "used_up", max_uses: 2, accepted_count: 2 }),
        invite({ id: "expired", expires_at: "2020-01-01T00:00:00Z" })
      ]
    });
    await openInviteTab();

    expect(screen.getAllByText(/· Active/)).toHaveLength(1);
    expect(screen.getAllByText(/· Inactive/)).toHaveLength(3);
  });

  it("never shows a token for invites loaded from the list (the API redacts it)", async () => {
    renderModal({ shares: [], invites: [invite({ id: "listed", token: null })] });
    await openInviteTab();

    expect(screen.queryByText(/workspace-invites\//)).toBeNull();
  });

  it("reveals the accept URL once, right after creating an invite", async () => {
    const fresh = invite({ id: "fresh", token: "tok_secret", role: "viewer" });
    api.createWorkspaceInvite.mockImplementation(async () => {
      // After creation the list endpoint returns the invite with its token redacted.
      api.listWorkspaceCollaboration.mockResolvedValue({ shares: [], invites: [{ ...fresh, token: null }] });
      return fresh;
    });
    const { onActivity } = renderModal({ shares: [], invites: [] });
    await openInviteTab();

    fireEvent.click(screen.getByRole("button", { name: "Create invite link" }));

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("Created invite link (viewer)"));
    expect(api.createWorkspaceInvite).toHaveBeenCalledWith("ws_1", expect.objectContaining({ role: "viewer", expires_in_hours: 168 }));
    expect(await screen.findByText(/api\.test\/api\/v1\/workspace-invites\/tok_secret\/accept/)).toBeTruthy();

    // Reopening the dialog: the token lives only in component state, so it is gone.
    cleanup();
    const reopened = renderModalWith({ shares: [], invites: [{ ...fresh, token: null }] });
    fireEvent.click(await screen.findByRole("button", { name: /Invite link/ }));
    expect(screen.queryByText(/tok_secret/)).toBeNull();
    reopened.onClose();
  });

  it("reports a failed invite creation with the request ref", async () => {
    api.createWorkspaceInvite.mockRejectedValue(
      new HelixOSApiError(403, "forbidden", "Owner role required", {}, "req_inv")
    );
    const { onActivity } = renderModal({ shares: [], invites: [] });
    await openInviteTab();

    fireEvent.click(screen.getByRole("button", { name: "Create invite link" }));

    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("Owner role required (ref req_inv)"));
  });
});

describe("ShareWorkspaceModal dialog behaviour", () => {
  it("closes on Escape and on the close button", async () => {
    const { onClose } = renderModal({ shares: [], invites: [] });
    await screen.findByRole("dialog");

    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(within(screen.getByRole("dialog")).getByLabelText("Close"));

    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
