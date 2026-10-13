import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HelixOSApiError } from "@helixos/api-client";
import type { OrgMembers, OrgRole } from "@helixos/types";

import { api, makeQueryClient, resetApi, wrapperFor } from "./helpers";

vi.mock("../lib/api-config", () => ({
  createHelixClient: () => api,
  getApiBaseUrl: () => "http://api.test"
}));

import { MembersView } from "../components/members-view";

const roster: OrgMembers = {
  members: [
    { user_id: "usr_1", email: "ada@lab.test", display_name: "Ada", role: "admin", joined_at: "2026-01-01T00:00:00Z" },
    { user_id: "usr_2", email: "bo@lab.test", display_name: null, role: "scientist", joined_at: "2026-01-02T00:00:00Z" }
  ],
  invites: [
    { id: "minv_1", email: "later@lab.test", role: "technician", invited_by: "usr_1", created_at: "2026-01-03T00:00:00Z" }
  ]
};

function renderView(role: OrgRole | null) {
  api.listOrganizationMembers.mockResolvedValue(roster);
  const onActivity = vi.fn();
  render(<MembersView organizationId="org_acme" role={role} apiEnabled onActivity={onActivity} />, {
    wrapper: wrapperFor(makeQueryClient())
  });
  return { onActivity };
}

beforeEach(resetApi);
afterEach(cleanup);

describe("MembersView", () => {
  it("shows the roster read-only to non-admins", async () => {
    renderView("scientist");
    expect(await screen.findByText("ada@lab.test")).toBeTruthy();
    expect(screen.getByText("Only organization admins can change membership.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add member" })).toBeNull();
    expect(screen.queryByText("Remove")).toBeNull();
    expect(screen.queryByText("Revoke")).toBeNull();
    expect(screen.getByText("Technician")).toBeTruthy();
  });

  it("lets an admin invite someone and reports it", async () => {
    api.addOrganizationMember.mockResolvedValue({ member: null, invite: roster.invites[0] });
    const { onActivity } = renderView("admin");
    await screen.findByText("ada@lab.test");

    fireEvent.change(screen.getByPlaceholderText("colleague@lab.org"), { target: { value: " new@lab.test " } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "qa_reviewer" } });
    fireEvent.click(screen.getByRole("button", { name: "Add member" }));

    await waitFor(() =>
      expect(api.addOrganizationMember).toHaveBeenCalledWith("org_acme", { email: "new@lab.test", role: "qa_reviewer" })
    );
    await waitFor(() => expect(onActivity).toHaveBeenCalledWith("Invited new@lab.test"));
  });

  it("changes a role and needs a second click to remove someone", async () => {
    api.changeMemberRole.mockResolvedValue({ ...roster.members[1], role: "pi" });
    api.removeOrganizationMember.mockResolvedValue(undefined);
    renderView("admin");
    await screen.findByText("bo@lab.test");

    fireEvent.change(screen.getByLabelText("Role for bo@lab.test"), { target: { value: "pi" } });
    await waitFor(() => expect(api.changeMemberRole).toHaveBeenCalledWith("org_acme", "usr_2", "pi"));

    const row = screen.getByText("bo@lab.test").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByText("Remove"));
    expect(api.removeOrganizationMember).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByText("Confirm remove"));
    await waitFor(() => expect(api.removeOrganizationMember).toHaveBeenCalledWith("org_acme", "usr_2"));
  });

  it("surfaces the server's reason, such as the last-admin rule", async () => {
    api.changeMemberRole.mockRejectedValue(
      new HelixOSApiError(409, "last_admin", "An organization must keep at least one admin", {}, "req_9")
    );
    renderView("admin");
    await screen.findByText("ada@lab.test");

    fireEvent.change(screen.getByLabelText("Role for ada@lab.test"), { target: { value: "scientist" } });
    expect((await screen.findByRole("alert")).textContent).toContain("must keep at least one admin (ref req_9)");
  });
});
