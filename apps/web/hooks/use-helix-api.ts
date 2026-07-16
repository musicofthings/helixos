"use client";

import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DatasetType, SampleType, WorkspaceCategory } from "@helixos/types";

import { createHelixClient } from "../lib/api-config";
import {
  toApiStatus,
  toExperimentCreatePayload,
  toExperimentViewModel,
  toVersionViewModel,
  type StatusLabel
} from "../lib/experiment-display";

export function invalidateAuditEvents(queryClient: ReturnType<typeof useQueryClient>, organizationId?: string) {
  return queryClient.invalidateQueries({ queryKey: ["audit-events", organizationId] });
}

export function useOrganizations(enabled = true) {
  return useQuery({
    queryKey: ["organizations"],
    enabled,
    queryFn: async () => createHelixClient().listOrganizations()
  });
}

export function useExperiments(organizationId?: string, enabled = true) {
  return useQuery({
    queryKey: ["experiments", organizationId],
    // Without the organizationId guard this fires before the org resolves and
    // returns experiments across every org the token can see.
    enabled: enabled && Boolean(organizationId),
    queryFn: async () => {
      const experiments = await createHelixClient().listExperiments({ organizationId });
      return experiments.map(toExperimentViewModel);
    }
  });
}

export function useExperimentVersions(experimentId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["experiment-versions", experimentId],
    enabled: enabled && Boolean(experimentId),
    queryFn: async () => {
      if (!experimentId) {
        return [];
      }
      const versions = await createHelixClient().listExperimentVersions(experimentId);
      return versions.map(toVersionViewModel);
    }
  });
}

export function useCreateExperiment(organizationId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      name: string;
      projectId?: string;
      blocks: string[];
    }) => {
      const experiment = await createHelixClient().createExperiment(toExperimentCreatePayload(input));
      return toExperimentViewModel(experiment);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useUpdateVersionStatus(organizationId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: { experimentId: string; versionId: string; status: StatusLabel }) => {
      const version = await createHelixClient().updateVersionStatus(input.experimentId, input.versionId, {
        status: toApiStatus(input.status)
      });
      return toVersionViewModel(version);
    },
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
      await queryClient.invalidateQueries({ queryKey: ["experiment-versions", variables.experimentId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useWorkspaces(organizationId?: string, enabled = true) {
  return useQuery({
    queryKey: ["workspaces", organizationId],
    enabled: enabled && Boolean(organizationId),
    queryFn: async () => createHelixClient().listWorkspaces(organizationId)
  });
}

export function useSeedDefaultWorkspaces(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (orgId: string) => createHelixClient().seedDefaultWorkspaces(orgId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspaces", organizationId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useCreateWorkspace(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      name: string;
      category: WorkspaceCategory;
      subcategory?: string | null;
      description?: string;
    }) =>
      createHelixClient().createWorkspace({
        organization_id: input.organizationId,
        name: input.name,
        category: input.category,
        subcategory: input.subcategory ?? null,
        description: input.description
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspaces", organizationId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useDeleteWorkspace(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (workspaceId: string) => createHelixClient().deleteWorkspace(workspaceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspaces", organizationId] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useDeleteProject(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (projectId: string) => createHelixClient().deleteProject(projectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useDeleteExperiment(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (experimentId: string) => createHelixClient().deleteExperiment(experimentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useProjects(params: { organizationId?: string; workspaceId?: string }, enabled = true) {
  return useQuery({
    queryKey: ["projects", params.organizationId, params.workspaceId],
    enabled: enabled && Boolean(params.organizationId) && Boolean(params.workspaceId),
    queryFn: async () =>
      createHelixClient().listProjects({
        organizationId: params.organizationId,
        workspaceId: params.workspaceId
      })
  });
}

export function useCreateProject(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      workspaceId: string;
      name: string;
      description?: string;
    }) =>
      createHelixClient().createProject({
        organization_id: input.organizationId,
        workspace_id: input.workspaceId,
        name: input.name,
        description: input.description
      }),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["projects", organizationId, variables.workspaceId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useCommitVersion(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { experimentId: string; message: string; blocks: string[] }) => {
      const version = await createHelixClient().commitExperimentVersion(input.experimentId, {
        message: input.message,
        blocks: input.blocks.map((content) => ({ type: "text" as const, content }))
      });
      return toVersionViewModel(version);
    },
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
      await queryClient.invalidateQueries({ queryKey: ["experiment-versions", variables.experimentId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useSamples(experimentId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["samples", experimentId],
    enabled: enabled && Boolean(experimentId),
    queryFn: async () => {
      if (!experimentId) {
        return [];
      }
      return createHelixClient().listSamples(experimentId);
    }
  });
}

export function useCreateSample(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      experimentId: string;
      name: string;
      sampleType: SampleType;
      wellPosition?: string;
    }) =>
      createHelixClient().createSample({
        organization_id: input.organizationId,
        experiment_id: input.experimentId,
        name: input.name,
        sample_type: input.sampleType,
        well_position: input.wellPosition ?? null
      }),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["samples", variables.experimentId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useDatasets(sampleId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["datasets", sampleId],
    enabled: enabled && Boolean(sampleId),
    queryFn: async () => {
      if (!sampleId) {
        return [];
      }
      return createHelixClient().listDatasets(sampleId);
    }
  });
}

export function useCreateDataset(organizationId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      sampleId: string;
      name: string;
      datasetType: DatasetType;
      content?: Record<string, unknown>;
    }) =>
      createHelixClient().createDataset({
        organization_id: input.organizationId,
        sample_id: input.sampleId,
        name: input.name,
        dataset_type: input.datasetType,
        content: input.content ?? {}
      }),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["datasets", variables.sampleId] });
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useSequence(sequenceId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["sequence", sequenceId],
    enabled: enabled && Boolean(sequenceId),
    queryFn: async () => {
      if (!sequenceId) {
        throw new Error("Sequence id is required");
      }
      return createHelixClient().getSequence(sequenceId);
    }
  });
}

export function useConnectors(enabled = true) {
  return useQuery({
    queryKey: ["connectors"],
    enabled,
    queryFn: async () => createHelixClient().listConnectors()
  });
}

export function useRunConnectorJob(organizationId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      connectorId: string;
      tool: string;
      arguments?: Record<string, unknown>;
    }) =>
      createHelixClient().runConnectorJob({
        organization_id: input.organizationId,
        connector_id: input.connectorId,
        tool: input.tool,
        arguments: input.arguments
      }),
    onSuccess: async () => {
      await invalidateAuditEvents(queryClient, organizationId);
    }
  });
}

export function useAuditEvents(organizationId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["audit-events", organizationId],
    enabled: enabled && Boolean(organizationId),
    queryFn: async () => {
      if (!organizationId) {
        return [];
      }
      return createHelixClient().listAuditEvents(organizationId);
    }
  });
}

export function useAgentSession(organizationId: string | undefined, enabled = true) {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [error, setError] = useState<Error | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    if (!organizationId || !enabled) {
      return;
    }

    let cancelled = false;

    async function createSession() {
      setIsPending(true);
      setError(null);
      try {
        const session = await createHelixClient().createAgentSession(organizationId!);
        if (!cancelled) {
          setSessionId(session.id);
          await invalidateAuditEvents(queryClient, organizationId);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      } finally {
        if (!cancelled) {
          setIsPending(false);
        }
      }
    }

    setSessionId(undefined);
    void createSession();

    return () => {
      cancelled = true;
    };
  }, [enabled, organizationId, queryClient, retryCount]);

  const retry = useCallback(() => setRetryCount((count) => count + 1), []);

  return { sessionId, isPending, error, retry };
}
