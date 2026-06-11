"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createHelixClient } from "../lib/api-config";
import {
  toApiStatus,
  toExperimentCreatePayload,
  toExperimentViewModel,
  type ExperimentViewModel
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

export function useExperiments(enabled = true) {
  return useQuery({
    queryKey: ["experiments"],
    enabled,
    queryFn: async () => {
      const experiments = await createHelixClient().listExperiments();
      return experiments.map(toExperimentViewModel);
    }
  });
}

export function useCreateExperiment(organizationId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      organizationId: string;
      title: string;
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

export function useUpdateExperimentStatus(organizationId?: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: { experimentId: string; status: ExperimentViewModel["status"] }) => {
      const experiment = await createHelixClient().updateExperimentStatus(input.experimentId, {
        status: toApiStatus(input.status)
      });
      return toExperimentViewModel(experiment);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["experiments"] });
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
    mutationFn: async (input: { connectorId: string; tool: string; arguments?: Record<string, unknown> }) =>
      createHelixClient().runConnectorJob({
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
  }, [enabled, organizationId, queryClient]);

  return { sessionId, isPending, error };
}
