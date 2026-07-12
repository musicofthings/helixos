"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ChevronRight, FolderPlus, LayoutGrid, LoaderCircle, Plus } from "lucide-react";
import type { WorkspaceCategory } from "@helixos/types";

import {
  useCreateExperiment,
  useCreateProject,
  useCreateWorkspace,
  useExperiments,
  useProjects,
  useSeedDefaultWorkspaces,
  useWorkspaces
} from "../../hooks/use-helix-api";
import { ExperimentDetail } from "./experiment-detail";

const WORKSPACE_CATEGORIES: WorkspaceCategory[] = [
  "molecular_biology",
  "biochemistry",
  "microbiology",
  "genomics",
  "cell_biology",
  "custom"
];

function categoryLabel(category: string): string {
  return category
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function LabView({
  organizationId,
  apiEnabled,
  selectedExperimentId,
  onSelectExperiment,
  onActivity
}: {
  organizationId?: string;
  apiEnabled: boolean;
  selectedExperimentId?: string;
  onSelectExperiment: (id: string | undefined) => void;
  onActivity: (message: string) => void;
}) {
  const workspacesQuery = useWorkspaces(organizationId, apiEnabled);
  const seedWorkspaces = useSeedDefaultWorkspaces(organizationId);
  const createWorkspace = useCreateWorkspace(organizationId);
  const createProject = useCreateProject(organizationId);
  const createExperiment = useCreateExperiment(organizationId);

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
  const [workspaceName, setWorkspaceName] = useState("");
  const [workspaceCategory, setWorkspaceCategory] = useState<WorkspaceCategory>("molecular_biology");
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [showExperimentForm, setShowExperimentForm] = useState(false);
  const [experimentName, setExperimentName] = useState("");

  // Auto-select the first item as lists load so the workbench is never empty.
  useEffect(() => {
    if (!selectedWorkspaceId && workspaces.length > 0) {
      setSelectedWorkspaceId(workspaces[0].id);
    }
  }, [selectedWorkspaceId, workspaces]);

  useEffect(() => {
    setSelectedProjectId(undefined);
  }, [selectedWorkspaceId]);

  useEffect(() => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    const stillVisible = experiments.some((experiment) => experiment.id === selectedExperimentId);
    const next = experiments[0]?.id;
    if (!stillVisible && selectedExperimentId !== next) {
      onSelectExperiment(next);
    }
  }, [experiments, onSelectExperiment, selectedExperimentId]);

  const selectedWorkspace = workspaces.find((workspace) => workspace.id === selectedWorkspaceId);
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedExperiment =
    experiments.find((experiment) => experiment.id === selectedExperimentId) ?? null;

  function submitWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceName.trim() || !organizationId) return;
    createWorkspace.mutate(
      { organizationId, name: workspaceName.trim(), category: workspaceCategory },
      {
        onSuccess: (workspace) => {
          onActivity(`Created workspace ${workspace.name}`);
          setSelectedWorkspaceId(workspace.id);
          setWorkspaceName("");
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
                  subtitle={categoryLabel(workspace.category)}
                />
              ))
            )}
            {showWorkspaceForm ? (
              <form onSubmit={submitWorkspace} className="mt-1 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-2">
                <input
                  value={workspaceName}
                  onChange={(event) => setWorkspaceName(event.target.value)}
                  placeholder="Workspace name"
                  className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                />
                <select
                  value={workspaceCategory}
                  onChange={(event) => setWorkspaceCategory(event.target.value as WorkspaceCategory)}
                  className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                >
                  {WORKSPACE_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {categoryLabel(category)}
                    </option>
                  ))}
                </select>
                <SubmitButton pending={createWorkspace.isPending} label="Create workspace" />
              </form>
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
  subtitle
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  subtitle?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md border px-2.5 py-2 text-left transition ${
        active ? "border-fern bg-[#edf5ef]" : "border-black/10 hover:bg-black/5"
      }`}
    >
      <div className="truncate text-sm font-medium text-ink">{title}</div>
      {subtitle ? <div className="mt-0.5 truncate text-[11px] text-graphite">{subtitle}</div> : null}
    </button>
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
