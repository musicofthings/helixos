import type { Experiment, ExperimentBlock, ExperimentStatus } from "@helixos/types";

export type ExperimentViewModel = {
  id: string;
  title: string;
  project: string;
  owner: string;
  status: "Draft" | "In review" | "Signed";
  updated: string;
  blocks: string[];
  organizationId: string;
  raw: Experiment;
};

const STATUS_LABELS: Record<ExperimentStatus, ExperimentViewModel["status"]> = {
  draft: "Draft",
  in_review: "In review",
  signed: "Signed",
  amended: "In review",
  archived: "Signed"
};

export function formatExperimentTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Recently";
  }

  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short"
  }).format(date);
}

export function blockToText(block: ExperimentBlock): string {
  if (typeof block.content === "string") {
    return block.content;
  }

  if (block.content && typeof block.content === "object" && "text" in block.content) {
    const text = (block.content as { text?: unknown }).text;
    if (typeof text === "string") {
      return text;
    }
  }

  return JSON.stringify(block.content);
}

export function toExperimentViewModel(experiment: Experiment): ExperimentViewModel {
  return {
    id: experiment.id,
    title: experiment.title,
    project: experiment.project_id ?? "General",
    owner: "Lab team",
    status: STATUS_LABELS[experiment.status],
    updated: formatExperimentTimestamp(experiment.updated_at),
    blocks: experiment.blocks.map(blockToText),
    organizationId: experiment.organization_id,
    raw: experiment
  };
}

export function toExperimentCreatePayload(input: {
  organizationId: string;
  title: string;
  projectId?: string;
  blocks: string[];
}) {
  return {
    organization_id: input.organizationId,
    title: input.title,
    project_id: input.projectId,
    blocks: input.blocks.map((content) => ({
      type: "text" as const,
      content
    }))
  };
}

export function toApiStatus(status: ExperimentViewModel["status"]): ExperimentStatus {
  const map: Record<ExperimentViewModel["status"], ExperimentStatus> = {
    Draft: "draft",
    "In review": "in_review",
    Signed: "signed"
  };
  return map[status];
}

export function canTransitionExperiment(
  from: ExperimentViewModel["status"],
  to: ExperimentViewModel["status"]
): boolean {
  if (from === to) return false;
  if (from === "Signed") return false;
  if (to === "In review") return from === "Draft";
  if (to === "Signed") return from === "In review";
  return false;
}
