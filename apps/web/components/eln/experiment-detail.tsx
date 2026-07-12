"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { GitCommitHorizontal, LoaderCircle, Plus, TestTube2 } from "lucide-react";
import type { DatasetType, SampleType } from "@helixos/types";

import {
  useCommitVersion,
  useCreateDataset,
  useCreateSample,
  useDatasets,
  useExperimentVersions,
  useSamples,
  useUpdateVersionStatus
} from "../../hooks/use-helix-api";
import {
  canTransitionExperiment,
  type ExperimentViewModel,
  type StatusLabel,
  type VersionViewModel
} from "../../lib/experiment-display";
import { PlateGrid, SAMPLE_TYPE_STYLES } from "./plate-grid";

const SAMPLE_TYPES: SampleType[] = ["dna", "rna", "protein", "cell", "tissue", "reagent", "other"];
const DATASET_TYPES: DatasetType[] = [
  "dna_sequence",
  "rna_sequence",
  "protein_sequence",
  "measurement",
  "file",
  "other"
];

const STATUS_CHIP: Record<StatusLabel, string> = {
  Draft: "bg-[#eef1ed] text-graphite",
  "In review": "bg-amber-50 text-amber-700",
  Signed: "bg-emerald-50 text-emerald-700"
};

export function ExperimentDetail({
  organizationId,
  apiEnabled,
  experiment,
  onActivity
}: {
  organizationId?: string;
  apiEnabled: boolean;
  experiment: ExperimentViewModel;
  onActivity: (message: string) => void;
}) {
  const versionsQuery = useExperimentVersions(experiment.id, apiEnabled);
  const samplesQuery = useSamples(experiment.id, apiEnabled);
  const updateVersionStatus = useUpdateVersionStatus(organizationId);
  const commitVersion = useCommitVersion(organizationId);
  const createSample = useCreateSample(organizationId);
  const createDataset = useCreateDataset(organizationId);

  const versions = useMemo(() => versionsQuery.data ?? [], [versionsQuery.data]);
  const samples = useMemo(() => samplesQuery.data ?? [], [samplesQuery.data]);

  const headVersion = useMemo<VersionViewModel | null>(() => {
    if (!versions.length) return null;
    const head = experiment.headVersionId
      ? versions.find((version) => version.id === experiment.headVersionId)
      : undefined;
    return head ?? versions[versions.length - 1];
  }, [experiment.headVersionId, versions]);

  const [selectedSampleId, setSelectedSampleId] = useState<string | undefined>();
  const [sampleName, setSampleName] = useState("");
  const [sampleType, setSampleType] = useState<SampleType>("dna");
  const [sampleWell, setSampleWell] = useState("");
  const [commitOpen, setCommitOpen] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [commitBlocks, setCommitBlocks] = useState("");

  useEffect(() => {
    setSelectedSampleId(undefined);
  }, [experiment.id]);

  const selectedSample = samples.find((sample) => sample.id === selectedSampleId) ?? null;
  const datasetsQuery = useDatasets(selectedSample?.id, apiEnabled);
  const datasets = datasetsQuery.data ?? [];

  const status = headVersion?.status ?? "Draft";
  const canReview = Boolean(headVersion) && canTransitionExperiment(status, "In review");
  const canSign = Boolean(headVersion) && canTransitionExperiment(status, "Signed");

  function transition(next: StatusLabel) {
    if (!headVersion) return;
    updateVersionStatus.mutate(
      { experimentId: experiment.id, versionId: headVersion.id, status: next },
      {
        onSuccess: (version) => onActivity(`${experiment.id} v${version.versionNumber} marked ${version.status}`),
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to update version")
      }
    );
  }

  function submitCommit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!commitMessage.trim()) return;
    const blocks = commitBlocks
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    commitVersion.mutate(
      { experimentId: experiment.id, message: commitMessage.trim(), blocks },
      {
        onSuccess: (version) => {
          onActivity(`Committed ${experiment.id} v${version.versionNumber}`);
          setCommitOpen(false);
          setCommitMessage("");
          setCommitBlocks("");
        },
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to commit version")
      }
    );
  }

  function submitSample(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sampleName.trim() || !organizationId) return;
    createSample.mutate(
      {
        organizationId,
        experimentId: experiment.id,
        name: sampleName.trim(),
        sampleType,
        wellPosition: sampleWell.trim() || undefined
      },
      {
        onSuccess: (sample) => {
          onActivity(`Added sample ${sample.name}${sample.well_position ? ` (${sample.well_position})` : ""}`);
          setSampleName("");
          setSampleWell("");
          setSelectedSampleId(sample.id);
        },
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to add sample")
      }
    );
  }

  function submitDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSample || !organizationId) return;
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const datasetType = String(form.get("dataset_type") ?? "other") as DatasetType;
    const value = String(form.get("value") ?? "").trim();
    if (!name) return;
    const content = value ? { value } : {};
    createDataset.mutate(
      { organizationId, sampleId: selectedSample.id, name, datasetType, content },
      {
        onSuccess: () => onActivity(`Attached dataset ${name} to ${selectedSample.name}`),
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to add dataset")
      }
    );
    event.currentTarget.reset();
  }

  return (
    <div className="grid gap-4">
      {/* Header */}
      <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-ink">{experiment.title}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-graphite">
              <span className={`rounded-md px-2 py-0.5 font-medium ${STATUS_CHIP[status]}`}>{status}</span>
              <span>{experiment.id}</span>
              <span>· {experiment.versionCount} version{experiment.versionCount === 1 ? "" : "s"}</span>
              <span>· {samples.length}/96 samples</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => transition("In review")}
              disabled={!canReview || updateVersionStatus.isPending}
              className="rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5 disabled:text-black/40"
            >
              Send review
            </button>
            <button
              onClick={() => transition("Signed")}
              disabled={!canSign || updateVersionStatus.isPending}
              className="rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5 disabled:text-black/40"
            >
              Sign
            </button>
            <button
              onClick={() => setCommitOpen((open) => !open)}
              className="inline-flex items-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c]"
            >
              <GitCommitHorizontal size={14} />
              Commit version
            </button>
          </div>
        </div>

        {commitOpen ? (
          <form onSubmit={submitCommit} className="mt-4 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3">
            <input
              value={commitMessage}
              onChange={(event) => setCommitMessage(event.target.value)}
              placeholder="Version message (e.g. Add gel image)"
              className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-fern"
            />
            <textarea
              value={commitBlocks}
              onChange={(event) => setCommitBlocks(event.target.value)}
              rows={4}
              placeholder="Content blocks, one per line"
              className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-fern"
            />
            <button
              disabled={!commitMessage.trim() || commitVersion.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
            >
              {commitVersion.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <GitCommitHorizontal size={14} />}
              Commit new version
            </button>
          </form>
        ) : null}
      </section>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        {/* Samples + plate */}
        <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <TestTube2 size={15} /> Samples ({samples.length}/96)
            </h3>
          </div>

          <div className="mt-4">
            <PlateGrid
              samples={samples}
              selectedSampleId={selectedSampleId}
              onSelectSample={setSelectedSampleId}
              onSelectEmptyWell={(well) => setSampleWell(well)}
            />
          </div>

          <form onSubmit={submitSample} className="mt-4 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3 sm:grid-cols-[1fr_auto_auto_auto]">
            <input
              value={sampleName}
              onChange={(event) => setSampleName(event.target.value)}
              placeholder="Sample name"
              className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-fern"
            />
            <select
              value={sampleType}
              onChange={(event) => setSampleType(event.target.value as SampleType)}
              className="rounded-md border border-black/10 bg-white px-2 py-2 text-sm outline-none focus:border-fern"
            >
              {SAMPLE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {SAMPLE_TYPE_STYLES[type].label}
                </option>
              ))}
            </select>
            <input
              value={sampleWell}
              onChange={(event) => setSampleWell(event.target.value.toUpperCase())}
              placeholder="Well"
              className="w-20 rounded-md border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-fern"
            />
            <button
              disabled={!sampleName.trim() || !organizationId || createSample.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
            >
              <Plus size={14} />
              Add
            </button>
          </form>
        </section>

        {/* Version history + datasets */}
        <div className="grid gap-4">
          <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-ink">Version history</h3>
            <div className="mt-3 grid gap-2">
              {versions.length ? (
                [...versions].reverse().map((version) => (
                  <div
                    key={version.id}
                    className={`rounded-md border p-2 text-xs ${
                      version.id === headVersion?.id ? "border-fern bg-[#edf5ef]" : "border-black/10"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-ink">v{version.versionNumber}</span>
                      <span className={`rounded px-1.5 py-0.5 ${STATUS_CHIP[version.status]}`}>{version.status}</span>
                    </div>
                    <div className="mt-1 text-graphite">{version.message}</div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-graphite">No versions yet.</div>
              )}
            </div>
          </section>

          <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-ink">
              Datasets {selectedSample ? `· ${selectedSample.name}` : ""}
            </h3>
            {selectedSample ? (
              <>
                <div className="mt-3 grid gap-2">
                  {datasets.length ? (
                    datasets.map((dataset) => (
                      <div key={dataset.id} className="rounded-md border border-black/10 p-2 text-xs">
                        <div className="font-semibold text-ink">{dataset.name}</div>
                        <div className="mt-1 text-graphite">{dataset.dataset_type}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-graphite">No datasets on this sample yet.</div>
                  )}
                </div>
                <form onSubmit={submitDataset} className="mt-3 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3">
                  <input
                    name="name"
                    placeholder="Dataset name"
                    className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-fern"
                  />
                  <select
                    name="dataset_type"
                    defaultValue="dna_sequence"
                    className="rounded-md border border-black/10 bg-white px-2 py-2 text-sm outline-none focus:border-fern"
                  >
                    {DATASET_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                  <input
                    name="value"
                    placeholder="Sequence / value (optional)"
                    className="rounded-md border border-black/10 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-fern"
                  />
                  <button
                    disabled={createDataset.isPending}
                    className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
                  >
                    <Plus size={14} />
                    Attach dataset
                  </button>
                </form>
              </>
            ) : (
              <p className="mt-3 text-xs text-graphite">Select a sample well to view and attach datasets.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
