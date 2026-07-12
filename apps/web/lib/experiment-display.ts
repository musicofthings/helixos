import type { Experiment, ExperimentBlock, ExperimentStatus, ExperimentVersion } from "@helixos/types";

export type StatusLabel = "Draft" | "In review" | "Signed";

export type ExperimentViewModel = {
  id: string;
  title: string;
  project: string;
  owner: string;
  updated: string;
  versionCount: number;
  headVersionId?: string | null;
  organizationId: string;
  raw: Experiment;
};

export type VersionViewModel = {
  id: string;
  experimentId: string;
  versionNumber: number;
  status: StatusLabel;
  message: string;
  blocks: string[];
  raw: ExperimentVersion;
};

const STATUS_LABELS: Record<ExperimentStatus, StatusLabel> = {
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
    title: experiment.name,
    project: experiment.project_id ?? "General",
    owner: "Lab team",
    updated: formatExperimentTimestamp(experiment.updated_at),
    versionCount: experiment.version_count,
    headVersionId: experiment.head_version_id,
    organizationId: experiment.organization_id,
    raw: experiment
  };
}

export function toVersionViewModel(version: ExperimentVersion): VersionViewModel {
  return {
    id: version.id,
    experimentId: version.experiment_id,
    versionNumber: version.version_number,
    status: STATUS_LABELS[version.status],
    message: version.message,
    blocks: version.blocks.map(blockToText),
    raw: version
  };
}

export function toExperimentCreatePayload(input: {
  organizationId: string;
  name: string;
  projectId?: string;
  blocks: string[];
}) {
  return {
    organization_id: input.organizationId,
    name: input.name,
    project_id: input.projectId,
    blocks: input.blocks.map((content) => ({
      type: "text" as const,
      content
    }))
  };
}

export function toApiStatus(status: StatusLabel): ExperimentStatus {
  const map: Record<StatusLabel, ExperimentStatus> = {
    Draft: "draft",
    "In review": "in_review",
    Signed: "signed"
  };
  return map[status];
}

export function canTransitionExperiment(from: StatusLabel, to: StatusLabel): boolean {
  if (from === to) return false;
  if (from === "Signed") return false;
  if (to === "In review") return from === "Draft";
  if (to === "Signed") return from === "In review";
  return false;
}
