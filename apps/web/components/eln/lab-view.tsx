"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, FolderPlus, LayoutGrid, LoaderCircle, Plus, Trash2 } from "lucide-react";
import type { WorkspaceCategory } from "@helixos/types";

import {
  useCreateExperiment,
  useCreateProject,
  useCreateWorkspace,
  useDeleteExperiment,
  useDeleteProject,
  useDeleteWorkspace,
  useExperiments,
  useProjects,
  useSeedDefaultWorkspaces,
  useWorkspaces
} from "../../hooks/use-helix-api";
import { categoryLabel } from "../../lib/workspace-taxonomy";
import { ExperimentDetail } from "./experiment-detail";
import { WorkspaceCreateForm } from "./workspace-create-form";

type DeleteTarget = { kind: "workspace" | "project" | "experiment"; id: string; name: string };

export function LabView({
  organizationId,
  apiEnabled,
  selectedExperimentId,
  onSelectExperiment,
  onActivity,
  newExperimentNonce = 0,
  resumeWorkspaceId,
  resumeNonce = 0,
  onResumeConsumed
}: {
  organizationId?: string;
  apiEnabled: boolean;
  selectedExperimentId?: string;
  onSelectExperiment: (id: string | undefined) => void;
  onActivity: (message: string) => void;
  newExperimentNonce?: number;
  /** One-shot resume target; consumed with ``resumeNonce``. */
  resumeWorkspaceId?: string;
  resumeNonce?: number;
  onResumeConsumed?: () => void;
}) {
  const workspacesQuery = useWorkspaces(organizationId, apiEnabled);
  const seedWorkspaces = useSeedDefaultWorkspaces(organizationId);
  const createWorkspace = useCreateWorkspace(organizationId);
  const deleteWorkspace = useDeleteWorkspace(organizationId);
  const createProject = useCreateProject(organizationId);
  const deleteProject = useDeleteProject(organizationId);
  const createExperiment = useCreateExperiment(organizationId);
  const deleteExperiment = useDeleteExperiment(organizationId);

  const workspaces = useMemo(() => workspacesQuery.data ?? [], [workspacesQuery.data]);

  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | undefined>();
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>();

  const projectsQuery = useProjects(
    { organizationId, workspaceId: selectedWorkspaceId },
    apiEnabled
  );
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);

  const experimentsQuery = useExperiments(organizationId, apiEnabled);
  const experiments = useMemo(
    () => (experimentsQuery.data ?? []).filter((experiment) => experiment.raw.project_id === selectedProjectId),
    [experimentsQuery.data, selectedProjectId]
  );

  const [showWorkspaceForm, setShowWorkspaceForm] = useState(false);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [showExperimentForm, setShowExperimentForm] = useState(false);
  const [experimentName, setExperimentName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  // Keep selections valid as lists load or entities are deleted: fall back to
  // the first available item, or clear when nothing remains.
  useEffect(() => {
    const stillThere = workspaces.some((workspace) => workspace.id === selectedWorkspaceId);
    if (!stillThere) {
      setSelectedWorkspaceId(workspaces[0]?.id);
    }
  }, [workspaces, selectedWorkspaceId]);

  // One-shot resume from the Workspace tab: apply once per nonce, then clear.
  const handledResumeNonce = useRef(resumeNonce);
  useEffect(() => {
    if (!resumeWorkspaceId || resumeNonce === handledResumeNonce.current) return;
    if (!workspaces.some((workspace) => workspace.id === resumeWorkspaceId)) return;
    handledResumeNonce.current = resumeNonce;
    setSelectedWorkspaceId(resumeWorkspaceId);
    onResumeConsumed?.();
  }, [resumeWorkspaceId, resumeNonce, workspaces, onResumeConsumed]);

  useEffect(() => {
    setSelectedProjectId(undefined);
  }, [selectedWorkspaceId]);

  useEffect(() => {
    const stillThere = projects.some((project) => project.id === selectedProjectId);
    if (!stillThere) {
      setSelectedProjectId(projects[0]?.id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    const stillVisible = experiments.some((experiment) => experiment.id === selectedExperimentId);
    const next = experiments[0]?.id;
    if (!stillVisible && selectedExperimentId !== next) {
      onSelectExperiment(next);
    }
  }, [experiments, onSelectExperiment, selectedExperimentId]);

  // Header "New experiment" button raises an intent: open the experiment form
  // when a project is selected, otherwise guide the user to create the missing
  // parent first (experiments only exist nested under a project).
  const handledNonce = useRef(newExperimentNonce);
  useEffect(() => {
    if (newExperimentNonce === handledNonce.current) return;
    handledNonce.current = newExperimentNonce;
    if (selectedProjectId) {
      setShowExperimentForm(true);
    } else if (selectedWorkspaceId) {
      setShowProjectForm(true);
      onActivity("Pick or create a project, then add the experiment inside it");
    } else {
      setShowWorkspaceForm(true);
      onActivity("Create a workspace and project before adding an experiment");
    }
  }, [newExperimentNonce, onActivity, selectedProjectId, selectedWorkspaceId]);

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedExperiment =
    experiments.find((experiment) => experiment.id === selectedExperimentId) ?? null;

  function submitWorkspace(values: {
    name: string;
    category: WorkspaceCategory;
    subcategory: string | null;
  }) {
    if (!organizationId) return;
    createWorkspace.mutate(
      {
        organizationId,
        name: values.name,
        category: values.category,
        subcategory: values.subcategory
      },
      {
        onSuccess: (workspace) => {
          onActivity(`Created workspace ${workspace.name}`);
          setSelectedWorkspaceId(workspace.id);
          setShowWorkspaceForm(false);
        },
        onError: (error) => onActivity(error instanceof Error ? error.message : "Failed to create workspace")
      }
    );
  }

  function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim() || !organizationId || !selectedWorkspaceId) return;
    createProject.mutate(
      { organizationId, workspaceId: selectedWorkspaceId, name: projectName.trim() },
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
    if (kind === "workspace") {
      deleteWorkspace.mutate(id, { onSuccess: () => done(`Deleted workspace ${name}`), onError: fail });
    } else if (kind === "project") {
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

  const deleting = deleteWorkspace.isPending || deleteProject.isPending || deleteExperiment.isPending;

  return (
    <div className="mt-6 grid gap-4">
      {/* Breadcrumb */}
      <nav className="flex flex-wrap items-center gap-1 text-xs text-graphite">
        <LayoutGrid size={14} />
        <span className="font-medium text-ink">Lab</span>
        {selectedWorkspace ? (
          <>
            <ChevronRight size={12} />
            <span>{selectedWorkspace.name}</span>
          </>
        ) : null}
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
        {/* Navigator column */}
        <div className="grid content-start gap-4">
          {/* Workspaces */}
          <NavSection
            title="Workspaces"
            onAdd={() => setShowWorkspaceForm((open) => !open)}
            addLabel="New workspace"
          >
            {workspacesQuery.isLoading ? (
              <Loading />
            ) : workspaces.length === 0 ? (
              <div className="grid gap-2">
                <p className="text-xs text-graphite">No workspaces yet.</p>
                <button
                  onClick={() => organizationId && seedWorkspaces.mutate(organizationId)}
                  disabled={!organizationId || seedWorkspaces.isPending}
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed"
                >
                  {seedWorkspaces.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <FolderPlus size={14} />}
                  Seed default workspaces
                </button>
              </div>
            ) : (
              workspaces.map((workspace) => (
                <ListButton
                  key={workspace.id}
                  active={workspace.id === selectedWorkspaceId}
                  onClick={() => setSelectedWorkspaceId(workspace.id)}
                  title={workspace.name}
                  subtitle={
                    workspace.subcategory
                      ? `${categoryLabel(workspace.category)} · ${workspace.subcategory}`
                      : categoryLabel(workspace.category)
                  }
                  onDelete={() =>
                    setDeleteTarget({ kind: "workspace", id: workspace.id, name: workspace.name })
                  }
                  deleteLabel="Delete workspace"
                />
              ))
            )}
            {showWorkspaceForm ? (
              <WorkspaceCreateForm
                compact
                pending={createWorkspace.isPending}
                onSubmit={submitWorkspace}
                onCancel={() => setShowWorkspaceForm(false)}
              />
            ) : null}
          </NavSection>

          {/* Projects */}
          {selectedWorkspace ? (
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
          ) : null}

          {/* Experiments */}
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

        {/* Detail column */}
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
                {selectedProject ? "Select or create an experiment" : "Select a workspace and project"}
              </h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-graphite">
                Organize work as Workspace → Project → Experiment. Each experiment is versioned like git, holds up to 96
                samples on a plate, and each sample can carry DNA, RNA, protein, and other datasets.
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
    target.kind === "workspace"
      ? "and every project, experiment, sample, and dataset inside it"
      : target.kind === "project"
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
            onClick={onCancel}
            disabled={pending}
            className="rounded-md border border-black/10 px-3 py-1.5 text-sm font-medium hover:bg-black/5 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
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
      <button onClick={onClick} className="min-w-0 flex-1 px-2.5 py-2 text-left">
        <div className="truncate text-sm font-medium text-ink">{title}</div>
        {subtitle ? <div className="mt-0.5 truncate text-[11px] text-graphite">{subtitle}</div> : null}
      </button>
      {onDelete ? (
        <button
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
