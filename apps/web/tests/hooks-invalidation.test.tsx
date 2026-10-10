import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, makeQueryClient, resetApi, wrapperFor } from "./helpers";

vi.mock("../lib/api-config", () => ({
  createHelixClient: () => api,
  getApiBaseUrl: () => "http://api.test"
}));

import {
  useAcceptWorkspaceInvite,
  useCreateWorkspaceInvite,
  useCreateWorkspaceShare,
  useDeleteExperiment,
  useDeleteProject,
  useExperimentVersions,
  useRevokeWorkspaceShare,
  useUpdateVersionStatus,
  useUpdateWorkspaceShare
} from "../hooks/use-helix-api";

const ORG = "org_demo";

beforeEach(() => resetApi());

function setup() {
  const queryClient = makeQueryClient();
  const spy = vi.spyOn(queryClient, "invalidateQueries");
  const keys = () => spy.mock.calls.map(([filters]) => JSON.stringify((filters as { queryKey: unknown }).queryKey));
  return { queryClient, spy, keys, wrapper: wrapperFor(queryClient) };
}

type Case = {
  name: string;
  useHook: (org: string) => { mutateAsync: (input: never) => Promise<unknown> };
  method: string;
  input: unknown;
  expected: string[];
};

const CASES: Case[] = [
  {
    name: "createWorkspaceShare",
    useHook: (org) => useCreateWorkspaceShare(org),
    method: "createWorkspaceShare",
    input: { workspaceId: "ws_1", subject: "a@b.co", role: "viewer" },
    expected: [`["workspace-collaboration","ws_1"]`, `["audit-events","${ORG}"]`]
  },
  {
    name: "updateWorkspaceShare",
    useHook: (org) => useUpdateWorkspaceShare(org),
    method: "updateWorkspaceShare",
    input: { workspaceId: "ws_1", shareId: "s_1", role: "editor" },
    expected: [`["workspace-collaboration","ws_1"]`, `["audit-events","${ORG}"]`]
  },
  {
    name: "revokeWorkspaceShare",
    useHook: (org) => useRevokeWorkspaceShare(org),
    method: "revokeWorkspaceShare",
    input: { workspaceId: "ws_1", shareId: "s_1" },
    expected: [`["workspace-collaboration","ws_1"]`, `["audit-events","${ORG}"]`]
  },
  {
    name: "createWorkspaceInvite",
    useHook: (org) => useCreateWorkspaceInvite(org),
    method: "createWorkspaceInvite",
    input: { workspaceId: "ws_1", role: "viewer" },
    expected: [`["workspace-collaboration","ws_1"]`, `["workspaces"]`, `["audit-events","${ORG}"]`]
  },
  {
    name: "acceptWorkspaceInvite",
    useHook: (org) => useAcceptWorkspaceInvite(org),
    method: "acceptWorkspaceInvite",
    input: "tok_123",
    expected: [`["workspaces","${ORG}"]`, `["workspace-collaboration"]`, `["audit-events","${ORG}"]`]
  },
  {
    name: "deleteProject",
    useHook: (org) => useDeleteProject(org),
    method: "deleteProject",
    input: "proj_1",
    expected: [`["projects"]`, `["experiments"]`, `["audit-events","${ORG}"]`]
  },
  {
    name: "deleteExperiment",
    useHook: (org) => useDeleteExperiment(org),
    method: "deleteExperiment",
    input: "exp_1",
    expected: [`["experiments"]`, `["audit-events","${ORG}"]`]
  }
];

describe("mutation cache invalidation", () => {
  it.each(CASES)("$name invalidates the right queries on success", async (c) => {
    const { keys, wrapper } = setup();
    api[c.method].mockResolvedValue({ id: "ok", token: null });
    const { result } = renderHook(() => c.useHook(ORG), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(c.input as never);
    });

    expect(api[c.method]).toHaveBeenCalledTimes(1);
    expect(keys()).toEqual(c.expected);
  });

  it.each(CASES)("$name invalidates nothing when the request fails", async (c) => {
    const { spy, wrapper } = setup();
    api[c.method].mockRejectedValue(new Error("403 forbidden"));
    const { result } = renderHook(() => c.useHook(ORG), { wrapper });

    await act(async () => {
      await expect(result.current.mutateAsync(c.input as never)).rejects.toThrow("403 forbidden");
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it("version status update refreshes only the affected experiment's versions", async () => {
    const { keys, wrapper } = setup();
    api.updateVersionStatus.mockResolvedValue({
      id: "v1", experiment_id: "exp_1", version_number: 1, message: "m", status: "in_review",
      author_subject: "u", created_at: "2026-01-01T00:00:00Z", blocks: [], parent_version_id: null, organization_id: ORG
    });
    const { result } = renderHook(() => useUpdateVersionStatus(ORG), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ experimentId: "exp_1", versionId: "v1", status: "In review" } as never);
    });

    expect(keys()).toContain(`["experiment-versions","exp_1"]`);
    expect(keys()).not.toContain(`["experiment-versions","exp_2"]`);
  });

  it("surfaces the server error from a failed share so the UI can display it", async () => {
    const { wrapper } = setup();
    api.createWorkspaceShare.mockRejectedValue(new Error("Share subject must be a known user"));
    const { result } = renderHook(() => useCreateWorkspaceShare(ORG), { wrapper });

    act(() => result.current.mutate({ workspaceId: "ws_1", subject: "x", role: "viewer" }));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Share subject must be a known user");
  });
});

describe("experiment switching", () => {
  const version = (experiment: string, message: string) => ({
    id: `${experiment}_v1`, experiment_id: experiment, organization_id: ORG, version_number: 1,
    parent_version_id: null, message, status: "draft", blocks: [], author_subject: "u",
    created_at: "2026-01-01T00:00:00Z"
  });

  it("loads each experiment's versions under its own cache key without leaking the previous one", async () => {
    const { queryClient, wrapper } = setup();
    api.listExperimentVersions.mockImplementation(async (id: string) => [version(id, `msg for ${id}`)]);

    const { result, rerender } = renderHook(({ id }) => useExperimentVersions(id), {
      wrapper,
      initialProps: { id: "exp_a" as string | undefined }
    });
    await waitFor(() => expect(result.current.data?.[0]?.message).toBe("msg for exp_a"));

    rerender({ id: "exp_b" });
    // Never shows exp_a's data while exp_b is loading.
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.[0]?.message).toBe("msg for exp_b"));

    expect(api.listExperimentVersions.mock.calls.map(([id]) => id)).toEqual(["exp_a", "exp_b"]);
    expect(queryClient.getQueryData(["experiment-versions", "exp_a"])).toBeDefined();
  });

  it("does not fetch when no experiment is selected", () => {
    const { wrapper } = setup();
    renderHook(() => useExperimentVersions(undefined), { wrapper });
    expect(api.listExperimentVersions).not.toHaveBeenCalled();
  });

  it("switching back reuses the cache without refetching the first experiment's key from scratch", async () => {
    const { wrapper } = setup();
    api.listExperimentVersions.mockImplementation(async (id: string) => [version(id, id)]);
    const { result, rerender } = renderHook(({ id }) => useExperimentVersions(id), {
      wrapper,
      initialProps: { id: "exp_a" as string | undefined }
    });
    await waitFor(() => expect(result.current.data?.[0]?.message).toBe("exp_a"));
    rerender({ id: "exp_b" });
    await waitFor(() => expect(result.current.data?.[0]?.message).toBe("exp_b"));
    rerender({ id: "exp_a" });

    // Cached data is available immediately on the switch back.
    expect(result.current.data?.[0]?.message).toBe("exp_a");
  });
});
