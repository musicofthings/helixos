export type ExperimentStatus = "draft" | "in_review" | "signed" | "amended" | "archived";

export type ExperimentBlockType =
  | "text"
  | "table"
  | "protocol_steps"
  | "reagent_list"
  | "sequence"
  | "image"
  | "chart"
  | "ai_annotation";

export interface ExperimentBlock {
  type: ExperimentBlockType;
  content: unknown;
}

export interface Experiment {
  id: string;
  organization_id: string;
  project_id?: string;
  title: string;
  status: ExperimentStatus;
  blocks: ExperimentBlock[];
  created_at: string;
  updated_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export type MoleculeType = "dna" | "rna" | "protein";

export type Topology = "linear" | "circular";

export interface SequenceFeature {
  name: string;
  start: number;
  end: number;
  kind: string;
}

export interface Sequence {
  id: string;
  organization_id: string;
  name: string;
  molecule_type: MoleculeType;
  topology: Topology;
  length: number;
  features: SequenceFeature[];
  created_at: string;
  updated_at: string;
}
