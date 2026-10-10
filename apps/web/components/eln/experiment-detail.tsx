"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { GitCommitHorizontal, LoaderCircle, Plus, TestTube2, Trash2 } from "lucide-react";
import type { DatasetType, Sample, SampleStatus, SampleType } from "@helixos/types";

import {
  useCommitVersion,
  useCreateDataset,
  useCreateSample,
  useDatasets,
  useDeleteSample,
  useExperimentVersions,
  useSamples,
  useUpdateSample,
  useUpdateVersionStatus
} from "../../hooks/use-helix-api";
import {
  canTransitionExperiment,
  type ExperimentViewModel,
  type StatusLabel,
  type VersionViewModel
} from "../../lib/experiment-display";
import { PlateGrid, SAMPLE_TYPE_STYLES } from "./plate-grid";
import { errorMessage } from "../../lib/error-message";

const SAMPLE_TYPES: SampleType[] = ["dna", "rna", "protein", "cell", "tissue", "reagent", "other"];
const SAMPLE_STATUSES: SampleStatus[] = ["planned", "active", "consumed", "archived"];
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

type EmptyWellIntent = {
  well: string;
  mode: "choose" | "add" | "move";
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
  const updateSample = useUpdateSample(organizationId);
  const deleteSample = useDeleteSample(organizationId);
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
  const [addFormArmed, setAddFormArmed] = useState(false);
  const [emptyWellIntent, setEmptyWellIntent] = useState<EmptyWellIntent | null>(null);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editType, setEditType] = useState<SampleType>("dna");
  const [editWell, setEditWell] = useState("");
  const [editStatus, setEditStatus] = useState<SampleStatus>("planned");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [commitOpen, setCommitOpen] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [commitBlocks, setCommitBlocks] = useState("");
  const sampleNameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setSelectedSampleId(undefined);
    setEmptyWellIntent(null);
    setEditing(false);
    setConfirmDelete(false);
    setAddFormArmed(false);
  }, [experiment.id]);

  const selectedSample = samples.find((sample) => sample.id === selectedSampleId) ?? null;
  const datasetsQuery = useDatasets(selectedSample?.id, apiEnabled);
  const datasets = datasetsQuery.data ?? [];

  useEffect(() => {
    if (!selectedSample) {
      setEditing(false);
      setConfirmDelete(false);
      return;
    }
    setEditName(selectedSample.name);
    setEditType(selectedSample.sample_type);
    setEditWell(selectedSample.well_position ?? "");
    setEditStatus(selectedSample.status);
  }, [selectedSample]);

  const status = headVersion?.status ?? "Draft";
  const canReview = Boolean(headVersion) && canTransitionExperiment(status, "In review");
  const canSign = Boolean(headVersion) && canTransitionExperiment(status, "Signed");

  function transition(next: StatusLabel) {
    if (!headVersion) return;
    updateVersionStatus.mutate(
      { experimentId: experiment.id, versionId: headVersion.id, status: next },
      {
        onSuccess: (version) => onActivity(`${experiment.id} v${version.versionNumber} marked ${version.status}`),
        onError: (error) => onActivity(errorMessage(error, "Failed to update version"))
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
        onError: (error) => onActivity(errorMessage(error, "Failed to commit version"))
      }
    );
  }

  function armAddForm(well?: string) {
    if (well) setSampleWell(well);
    setAddFormArmed(true);
    setEmptyWellIntent(null);
    requestAnimationFrame(() => sampleNameRef.current?.focus());
  }

  function handleEmptyWell(well: string) {
    if (selectedSample) {
      setEmptyWellIntent({ well, mode: "choose" });
      return;
    }
    armAddForm(well);
  }

  function handleSelectSample(sampleId: string) {
    setSelectedSampleId(sampleId);
    setEmptyWellIntent(null);
    setAddFormArmed(false);
    setConfirmDelete(false);
  }

  function moveSelectedToWell(well: string) {
    if (!selectedSample) return;
    updateSample.mutate(
      {
        sampleId: selectedSample.id,
        experimentId: experiment.id,
        wellPosition: well
      },
      {
        onSuccess: (sample) => {
          onActivity(`Moved ${sample.name} to ${well}`);
          setEmptyWellIntent(null);
        },
        onError: (error) => onActivity(errorMessage(error, "Failed to move sample"))
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
          setAddFormArmed(false);
          setEmptyWellIntent(null);
          setSelectedSampleId(sample.id);
        },
        onError: (error) => onActivity(errorMessage(error, "Failed to add sample"))
      }
    );
  }

  function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSample || !editName.trim()) return;
    updateSample.mutate(
      {
        sampleId: selectedSample.id,
        experimentId: experiment.id,
        name: editName.trim(),
        sampleType: editType,
        wellPosition: editWell.trim() || null,
        status: editStatus
      },
      {
        onSuccess: (sample) => {
          onActivity(`Updated sample ${sample.name}`);
          setEditing(false);
        },
        onError: (error) => onActivity(errorMessage(error, "Failed to update sample"))
      }
    );
  }

  function confirmDeleteSample() {
    if (!selectedSample) return;
    const name = selectedSample.name;
    deleteSample.mutate(
      { sampleId: selectedSample.id, experimentId: experiment.id },
      {
        onSuccess: () => {
          onActivity(`Deleted sample ${name}`);
          setSelectedSampleId(undefined);
          setConfirmDelete(false);
        },
        onError: (error) => onActivity(errorMessage(error, "Failed to delete sample"))
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
        onError: (error) => onActivity(errorMessage(error, "Failed to add dataset"))
      }
    );
    event.currentTarget.reset();
  }

  return (
    <div className="grid gap-4">
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
              onSelectSample={handleSelectSample}
              onSelectEmptyWell={handleEmptyWell}
            />
          </div>

          {emptyWellIntent?.mode === "choose" && selectedSample ? (
            <div className="mt-3 rounded-md border border-fern/30 bg-[#edf5ef] p-3 text-sm">
              <p className="text-ink">
                Well <span className="font-semibold">{emptyWellIntent.well}</span> is empty. Sample{" "}
                <span className="font-semibold">{selectedSample.name}</span> is selected.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => moveSelectedToWell(emptyWellIntent.well)}
                  disabled={updateSample.isPending}
                  className="rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:bg-black/20"
                >
                  Move here
                </button>
                <button
                  type="button"
                  onClick={() => armAddForm(emptyWellIntent.well)}
                  className="rounded-md border border-black/10 bg-white px-3 py-1.5 text-xs font-medium hover:bg-black/5"
                >
                  Add new
                </button>
                <button
                  type="button"
                  onClick={() => setEmptyWellIntent(null)}
                  className="rounded-md px-3 py-1.5 text-xs font-medium text-graphite hover:bg-black/5"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          <form
            onSubmit={submitSample}
            className={`mt-4 grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_auto_auto_auto] ${
              addFormArmed ? "border-fern bg-[#edf5ef]" : "border-black/10 bg-[#fbfbf8]"
            }`}
          >
            {addFormArmed ? (
              <p className="sm:col-span-4 text-[11px] font-medium text-fern">
                Adding sample{sampleWell ? ` to ${sampleWell}` : ""}…
              </p>
            ) : null}
            <input
              ref={sampleNameRef}
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

        <div className="grid gap-4 content-start">
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

          <SampleDetailPanel
            sample={selectedSample}
            datasets={datasets}
            datasetsLoading={datasetsQuery.isLoading}
            editing={editing}
            editName={editName}
            editType={editType}
            editWell={editWell}
            editStatus={editStatus}
            updatePending={updateSample.isPending}
            deletePending={deleteSample.isPending}
            createDatasetPending={createDataset.isPending}
            onClear={() => setSelectedSampleId(undefined)}
            onStartEdit={() => setEditing(true)}
            onCancelEdit={() => {
              setEditing(false);
              if (selectedSample) {
                setEditName(selectedSample.name);
                setEditType(selectedSample.sample_type);
                setEditWell(selectedSample.well_position ?? "");
                setEditStatus(selectedSample.status);
              }
            }}
            onEditName={setEditName}
            onEditType={setEditType}
            onEditWell={setEditWell}
            onEditStatus={setEditStatus}
            onSubmitEdit={submitEdit}
            onRequestDelete={() => setConfirmDelete(true)}
            onSubmitDataset={submitDataset}
          />
        </div>
      </div>

      {confirmDelete && selectedSample ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-lg border border-black/10 bg-white p-5 shadow-xl">
            <h3 className="text-sm font-semibold text-ink">Delete sample?</h3>
            <p className="mt-2 text-sm text-graphite">
              This permanently removes <span className="font-medium text-ink">{selectedSample.name}</span> and all
              datasets attached to it. This cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={deleteSample.isPending}
                className="rounded-md border border-black/10 px-3 py-1.5 text-sm font-medium hover:bg-black/5 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteSample}
                disabled={deleteSample.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
              >
                {deleteSample.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Trash2 size={14} />}
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SampleDetailPanel({
  sample,
  datasets,
  datasetsLoading,
  editing,
  editName,
  editType,
  editWell,
  editStatus,
  updatePending,
  deletePending,
  createDatasetPending,
  onClear,
  onStartEdit,
  onCancelEdit,
  onEditName,
  onEditType,
  onEditWell,
  onEditStatus,
  onSubmitEdit,
  onRequestDelete,
  onSubmitDataset
}: {
  sample: Sample | null;
  datasets: { id: string; name: string; dataset_type: string }[];
  datasetsLoading: boolean;
  editing: boolean;
  editName: string;
  editType: SampleType;
  editWell: string;
  editStatus: SampleStatus;
  updatePending: boolean;
  deletePending: boolean;
  createDatasetPending: boolean;
  onClear: () => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onEditName: (value: string) => void;
  onEditType: (value: SampleType) => void;
  onEditWell: (value: string) => void;
  onEditStatus: (value: SampleStatus) => void;
  onSubmitEdit: (event: FormEvent<HTMLFormElement>) => void;
  onRequestDelete: () => void;
  onSubmitDataset: (event: FormEvent<HTMLFormElement>) => void;
}) {
  if (!sample) {
    return (
      <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-ink">Sample detail</h3>
        <p className="mt-3 text-xs text-graphite">Select a sample well to view details, edit, or attach datasets.</p>
      </section>
    );
  }

  const typeStyle = SAMPLE_TYPE_STYLES[sample.sample_type];
  const metadataEntries = Object.entries(sample.metadata ?? {});

  return (
    <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">{sample.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-graphite">
            <span className={`rounded px-1.5 py-0.5 ${typeStyle.chip}`}>{typeStyle.label}</span>
            <span>{sample.well_position ?? "No well"}</span>
            <span>· {sample.status}</span>
          </div>
        </div>
        <button onClick={onClear} className="text-[11px] text-graphite hover:text-ink">
          Clear
        </button>
      </div>

      {metadataEntries.length ? (
        <div className="mt-3 rounded-md border border-black/10 bg-[#fbfbf8] p-2 text-[11px] text-graphite">
          {metadataEntries.map(([key, value]) => (
            <div key={key}>
              <span className="font-medium text-ink">{key}:</span> {String(value)}
            </div>
          ))}
        </div>
      ) : null}

      {editing ? (
        <form onSubmit={onSubmitEdit} className="mt-3 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3">
          <input
            value={editName}
            onChange={(event) => onEditName(event.target.value)}
            placeholder="Name"
            className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
          />
          <select
            value={editType}
            onChange={(event) => onEditType(event.target.value as SampleType)}
            className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
          >
            {SAMPLE_TYPES.map((type) => (
              <option key={type} value={type}>
                {SAMPLE_TYPE_STYLES[type].label}
              </option>
            ))}
          </select>
          <input
            value={editWell}
            onChange={(event) => onEditWell(event.target.value.toUpperCase())}
            placeholder="Well (optional)"
            className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
          />
          <select
            value={editStatus}
            onChange={(event) => onEditStatus(event.target.value as SampleStatus)}
            className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
          >
            {SAMPLE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <button
              disabled={!editName.trim() || updatePending}
              className="flex-1 rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:bg-black/20"
            >
              {updatePending ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={onCancelEdit}
              className="rounded-md border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-black/5"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={onStartEdit}
            className="rounded-md border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-black/5"
          >
            Edit
          </button>
          <button
            onClick={onRequestDelete}
            disabled={deletePending}
            className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            <Trash2 size={12} />
            Delete
          </button>
        </div>
      )}

      <div className="mt-4 border-t border-black/10 pt-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-graphite">Datasets</h4>
        <div className="mt-2 grid gap-2">
          {datasetsLoading ? (
            <div className="text-xs text-graphite">Loading…</div>
          ) : datasets.length ? (
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
        <form onSubmit={onSubmitDataset} className="mt-3 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-3">
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
            disabled={createDatasetPending}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
          >
            <Plus size={14} />
            Attach dataset
          </button>
        </form>
      </div>
    </section>
  );
}
