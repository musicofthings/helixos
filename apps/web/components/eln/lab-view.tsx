"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, LayoutGrid, LoaderCircle, Plus, Trash2 } from "lucide-react";
import type { Workspace } from "@helixos/types";

import {
  useCreateExperiment,
  useCreateProject,
  useDeleteExperiment,
  useDeleteProject,
  useExperiments,
  useProjects
} from "../../hooks/use-helix-api";
import { ExperimentDetail } from "./experiment-detail";

type DeleteTarget = { kind: "project" | "experiment"; id: string; name: string };

export function LabView({
  organizationId,
  workspace,
  apiEnabled,
  selectedExperimentId,
  onSelectExperiment,
  onActivity,
  newExperimentNonce = 0
}: {
  organizationId?: string;
  /** Active workspace from the shell sidebar; null shows an empty state. */
  workspace?: Workspace | null;
  apiEnabled: boolean;
  selectedExperimentId?: string;
  onSelectExperiment: (id: string | undefined) => void;
  onActivity: (message: string) => void;
  newExperimentNonce?: number;
}) {
  const workspaceId = workspace?.id;
  const createProject = useCreateProject(organizationId);
  const deleteProject = useDeleteProject(organizationId);
  const createExperiment = useCreateExperiment(organizationId);
  const deleteExperiment = useDeleteExperiment(organizationId);

  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>();

  const projectsQuery = useProjects({ organizationId, workspaceId }, apiEnabled && Boolean(workspaceId));
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);

  const experimentsQuery = useExperiments(organizationId, apiEnabled && Boolean(workspaceId));
  const experiments = useMemo(
    () => (experimentsQuery.data ?? []).filter((experiment) => experiment.raw.project_id === selectedProjectId),
    [experimentsQuery.data, selectedProjectId]
  );

  const [showProjectForm, setShowProjectForm] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [showExperimentForm, setShowExperimentForm] = useState(false);
  const [experimentName, setExperimentName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  useEffect(() => {
    setSelectedProjectId(undefined);
    setShowProjectForm(false);
    setShowExperimentForm(false);
  }, [workspaceId]);

  // Deep-link from workspace home: select the experiment's project before
  // filtering the lab list, otherwise the visibility effect clears the id.
  useEffect(() => {
    if (!selectedExperimentId) return;
    const target = (experimentsQuery.data ?? []).find(
      (experiment) => experiment.id === selectedExperimentId
    );
    const projectId = target?.raw.project_id;
    if (!projectId || projectId === selectedProjectId) return;
    if (projects.some((project) => project.id === projectId)) {
      setSelectedProjectId(projectId);
    }
  }, [selectedExperimentId, experimentsQuery.data, projects, selectedProjectId]);

  useEffect(() => {
    const stillThere = projects.some((project) => project.id === selectedProjectId);
    if (!stillThere) {
      // Prefer the project of a deep-linked experiment over the first project.
      const linked = (experimentsQuery.data ?? []).find(
        (experiment) => experiment.id === selectedExperimentId
      );
      const linkedProjectId = linked?.raw.project_id;
      if (linkedProjectId && projects.some((project) => project.id === linkedProjectId)) {
        setSelectedProjectId(linkedProjectId);
        return;
      }
      setSelectedProjectId(projects[0]?.id);
    }
  }, [projects, selectedProjectId, experimentsQuery.data, selectedExperimentId]);

  useEffect(() => {
    const stillVisible = experiments.some((experiment) => experiment.id === selectedExperimentId);
    if (stillVisible) return;
    // Wait for project switch when the selection lives in another project here.
    const target = (experimentsQuery.data ?? []).find(
      (experiment) => experiment.id === selectedExperimentId
    );
    if (
      target?.raw.project_id &&
      projects.some((project) => project.id === target.raw.project_id)
    ) {
      return;
    }
    const next = experiments[0]?.id;
    if (selectedExperimentId !== next) {
      onSelectExperiment(next);
    }
  }, [
    experiments,
    experimentsQuery.data,
    onSelectExperiment,
    projects,
    selectedExperimentId
  ]);

  // Header "New experiment" button raises an intent: open the experiment form
  // when a project is selected, otherwise guide the user to create the missing
  // parent first (experiments only exist nested under a project).
  const handledNonce = useRef(newExperimentNonce);
  useEffect(() => {
    if (newExperimentNonce === handledNonce.current) return;
    handledNonce.current = newExperimentNonce;
    if (!workspaceId) {
      onActivity("Select or create a workspace in the sidebar first");
      return;
    }
    if (selectedProjectId) {
      setShowExperimentForm(true);
    } else {
      setShowProjectForm(true);
      onActivity("Pick or create a project, then add the experiment inside it");
    }
  }, [newExperimentNonce, onActivity, selectedProjectId, workspaceId]);

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedExperiment =
    experiments.find((experiment) => experiment.id === selectedExperimentId) ?? null;

  function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim() || !organizationId || !workspaceId) return;
    createProject.mutate(
      { organizationId, workspaceId, name: projectName.trim() },
      {
        onSuccess: (project) => {
          onActivity(`Created project ${project.name}`);
          setSelectedProjectId(project.id);
          setProjectName("");
          setShowProjectForm(false);
        },
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to create project")
      }
    );
  }

  function submitExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!experimentName.trim() || !organizationId || !selectedProjectId) return;
    createExperiment.mutate(
      {
        organizationId,
        name: experimentName.trim(),
        projectId: selectedProjectId,
        blocks: ["Objective"]
      },
      {
        onSuccess: (experiment) => {
          onActivity(`Created experiment ${experiment.title}`);
          onSelectExperiment(experiment.id);
          setExperimentName("");
          setShowExperimentForm(false);
        },
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to create experiment")
      }
    );
  }

  function confirmDelete() {
    if (!deleteTarget) return;
    const { kind, id, name } = deleteTarget;
    const done = (message: string) => {
      onActivity(message);
      setDeleteTarget(null);
    };
    const fail = (error: unknown) =>
      onActivity(error instanceof Error ? error.message : `Failed to delete ${kind}`);
    if (kind === "project") {
      deleteProject.mutate(id, { onSuccess: () => done(`Deleted project ${name}`), onError: fail });
    } else {
      deleteExperiment.mutate(id, {
        onSuccess: () => {
          if (selectedExperimentId === id) onSelectExperiment(undefined);
          done(`Deleted experiment ${name}`);
        },
        onError: fail
      });
    }
  }

  const deleting = deleteProject.isPending || deleteExperiment.isPending;

  if (!workspace) {
    return (
      <div className="mt-6 rounded-md border border-dashed border-black/15 bg-white p-8 text-center shadow-sm">
        <h2 className="text-sm font-semibold text-ink">Select a workspace</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-graphite">
          Choose or create a workspace in the sidebar, then open the lab notebook to manage
          projects and experiments.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-6 grid gap-4">
      <nav className="flex flex-wrap items-center gap-1 text-xs text-graphite">
        <LayoutGrid size={14} />
        <span className="font-medium text-ink">Lab</span>
        <ChevronRight size={12} />
        <span>{workspace.name}</span>
        {selectedProject ? (
          <>
            <ChevronRight size={12} />
            <span>{selectedProject.name}</span>
          </>
        ) : null}
        {selectedExperiment ? (
          <>
            <ChevronRight size={12} />
            <span className="font-medium text-ink">{selectedExperiment.title}</span>
          </>
        ) : null}
      </nav>

      <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
        <div className="grid content-start gap-4">
          <NavSection
            title="Projects"
            onAdd={() => setShowProjectForm((open) => !open)}
            addLabel="New project"
          >
            {projectsQuery.isLoading ? (
              <Loading />
            ) : projects.length === 0 ? (
              <p className="text-xs text-graphite">No projects in this workspace yet.</p>
            ) : (
              projects.map((project) => (
                <ListButton
                  key={project.id}
                  active={project.id === selectedProjectId}
                  onClick={() => setSelectedProjectId(project.id)}
                  title={project.name}
                  subtitle={project.status}
                  onDelete={() => setDeleteTarget({ kind: "project", id: project.id, name: project.name })}
                  deleteLabel="Delete project"
                />
              ))
            )}
            {showProjectForm ? (
              <form onSubmit={submitProject} className="mt-1 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-2">
                <input
                  value={projectName}
                  onChange={(event) => setProjectName(event.target.value)}
                  placeholder="Project name"
                  className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                />
                <SubmitButton pending={createProject.isPending} label="Create project" />
              </form>
            ) : null}
          </NavSection>

          {selectedProject ? (
            <NavSection
              title="Experiments"
              onAdd={() => setShowExperimentForm((open) => !open)}
              addLabel="New experiment"
            >
              {experimentsQuery.isLoading ? (
                <Loading />
              ) : experiments.length === 0 ? (
                <p className="text-xs text-graphite">No experiments in this project yet.</p>
              ) : (
                experiments.map((experiment) => (
                  <ListButton
                    key={experiment.id}
                    active={experiment.id === selectedExperimentId}
                    onClick={() => onSelectExperiment(experiment.id)}
                    title={experiment.title}
                    subtitle={`v${experiment.versionCount} · ${experiment.updated}`}
                    onDelete={() =>
                      setDeleteTarget({ kind: "experiment", id: experiment.id, name: experiment.title })
                    }
                    deleteLabel="Delete experiment"
                  />
                ))
              )}
              {showExperimentForm ? (
                <form onSubmit={submitExperiment} className="mt-1 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-2">
                  <input
                    value={experimentName}
                    onChange={(event) => setExperimentName(event.target.value)}
                    placeholder="Experiment name"
                    className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                  />
                  <SubmitButton pending={createExperiment.isPending} label="Create experiment" />
                </form>
              ) : null}
            </NavSection>
          ) : null}
        </div>

        <div>
          {selectedExperiment ? (
            <ExperimentDetail
              organizationId={organizationId}
              apiEnabled={apiEnabled}
              experiment={selectedExperiment}
              onActivity={onActivity}
            />
          ) : (
            <section className="rounded-md border border-black/10 bg-white p-8 text-center shadow-sm">
              <h2 className="text-sm font-semibold text-ink">
                {selectedProject ? "Select or create an experiment" : "Select or create a project"}
              </h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-graphite">
                Work in this workspace as Project → Experiment. Each experiment is versioned like git,
                holds up to 96 samples on a plate, and each sample can carry DNA, RNA, protein, and
                other datasets.
              </p>
            </section>
          )}
        </div>
      </div>

      {deleteTarget ? (
        <ConfirmDeleteDialog
          target={deleteTarget}
          pending={deleting}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      ) : null}
    </div>
  );
}

function ConfirmDeleteDialog({
  target,
  pending,
  onCancel,
  onConfirm
}: {
  target: DeleteTarget;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const cascade =
    target.kind === "project"
      ? "and every experiment, sample, and dataset inside it"
      : "and all its versions, samples, and datasets";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-lg border border-black/10 bg-white p-5 shadow-xl">
        <h3 className="text-sm font-semibold text-ink">Delete {target.kind}?</h3>
        <p className="mt-2 text-sm text-graphite">
          This permanently removes <span className="font-medium text-ink">{target.name}</span> {cascade}. This cannot be
          undone.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="rounded-md border border-black/10 px-3 py-1.5 text-sm font-medium hover:bg-black/5 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="inline-flex items-center gap-2 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
          >
            {pending ? <LoaderCircle size={14} className="animate-spin" /> : <Trash2 size={14} />}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

function NavSection({
  title,
  addLabel,
  onAdd,
  children
}: {
  title: string;
  addLabel: string;
  onAdd: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-md border border-black/10 bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-graphite">{title}</h3>
        <button
          type="button"
          onClick={onAdd}
          aria-label={addLabel}
          title={addLabel}
          className="rounded-md border border-black/10 p-1 text-graphite hover:bg-black/5"
        >
          <Plus size={14} />
        </button>
      </div>
      <div className="mt-2 grid gap-1.5">{children}</div>
    </section>
  );
}

function ListButton({
  active,
  onClick,
  title,
  subtitle,
  onDelete,
  deleteLabel
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  subtitle?: string;
  onDelete?: () => void;
  deleteLabel?: string;
}) {
  return (
    <div
      className={`group flex items-center gap-1 rounded-md border pr-1 transition ${
        active ? "border-fern bg-[#edf5ef]" : "border-black/10 hover:bg-black/5"
      }`}
    >
      <button type="button" onClick={onClick} className="min-w-0 flex-1 px-2.5 py-2 text-left">
        <div className="truncate text-sm font-medium text-ink">{title}</div>
        {subtitle ? <div className="mt-0.5 truncate text-[11px] text-graphite">{subtitle}</div> : null}
      </button>
      {onDelete ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          aria-label={deleteLabel}
          title={deleteLabel}
          className="rounded p-1.5 text-graphite/50 transition hover:bg-red-50 hover:text-red-600 focus:text-red-600 group-hover:text-graphite"
        >
          <Trash2 size={14} />
        </button>
      ) : null}
    </div>
  );
}

function SubmitButton({ pending, label }: { pending: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
    >
      {pending ? <LoaderCircle size={14} className="animate-spin" /> : <Plus size={14} />}
      {label}
    </button>
  );
}

function Loading() {
  return (
    <div className="inline-flex items-center gap-2 text-xs text-graphite">
      <LoaderCircle size={14} className="animate-spin" /> Loading...
    </div>
  );
}
