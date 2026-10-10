"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  FlaskConical,
  LoaderCircle,
  Plus,
  Share2,
  Trash2
} from "lucide-react";
import type { Workspace } from "@helixos/types";

import {
  useCreateProject,
  useExperiments,
  useProjects
} from "../../hooks/use-helix-api";
import { errorMessage } from "../../lib/error-message";

export function WorkspaceHome({
  workspace,
  organizationId,
  apiEnabled,
  onOpenLab,
  onShare,
  onDelete,
  onActivity
}: {
  workspace: Workspace;
  organizationId?: string;
  apiEnabled: boolean;
  onOpenLab: (experimentId?: string) => void;
  onShare: () => void;
  onDelete: () => void;
  onActivity: (message: string) => void;
}) {
  const projectsQuery = useProjects(
    { organizationId, workspaceId: workspace.id },
    apiEnabled
  );
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const projectIds = useMemo(() => new Set(projects.map((project) => project.id)), [projects]);

  const experimentsQuery = useExperiments(organizationId, apiEnabled);
  const recentExperiments = useMemo(() => {
    return (experimentsQuery.data ?? [])
      .filter((experiment) => experiment.raw.project_id && projectIds.has(experiment.raw.project_id))
      .sort((a, b) => new Date(b.raw.updated_at).getTime() - new Date(a.raw.updated_at).getTime())
      .slice(0, 8);
  }, [experimentsQuery.data, projectIds]);

  const createProject = useCreateProject(organizationId);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [projectName, setProjectName] = useState("");

  function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectName.trim() || !organizationId) return;
    createProject.mutate(
      { organizationId, workspaceId: workspace.id, name: projectName.trim() },
      {
        onSuccess: (project) => {
          onActivity(`Created project ${project.name}`);
          setProjectName("");
          setShowProjectForm(false);
        },
        onError: (error) =>
          onActivity(errorMessage(error, "Failed to create project"))
      }
    );
  }

  const isEmpty = projects.length === 0 && recentExperiments.length === 0;

  return (
    <div className="grid gap-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-graphite">Workspace home</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Get started in {workspace.name}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpenLab()}
            className="inline-flex items-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c]"
          >
            <FlaskConical size={14} />
            Open lab notebook
          </button>
          <button
            type="button"
            onClick={onShare}
            className="inline-flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5"
          >
            <Share2 size={14} />
            Share
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-50"
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      </header>

      {isEmpty ? (
        <section className="rounded-md border border-dashed border-black/15 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-ink">Get started</h3>
          <p className="mt-2 max-w-lg text-sm text-graphite">
            This workspace is empty. Create a project, then open the lab notebook to add
            experiments, samples, and versions.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setShowProjectForm(true)}
              className="inline-flex items-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c]"
            >
              <Plus size={14} />
              Create first project
            </button>
            <button
              type="button"
              onClick={() => onOpenLab()}
              className="inline-flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5"
            >
              <FlaskConical size={14} />
              Open lab notebook
            </button>
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink">Projects</h3>
            <button
              type="button"
              onClick={() => setShowProjectForm((open) => !open)}
              className="inline-flex items-center gap-1 rounded-md border border-black/10 px-2 py-1 text-[11px] font-medium hover:bg-black/5"
            >
              <Plus size={12} />
              New project
            </button>
          </div>
          {showProjectForm ? (
            <form onSubmit={submitProject} className="mb-3 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-2">
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="Project name"
                className="rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern"
                autoFocus
              />
              <button
                type="submit"
                disabled={createProject.isPending || !projectName.trim()}
                className="inline-flex w-fit items-center gap-2 rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {createProject.isPending ? <LoaderCircle size={14} className="animate-spin" /> : null}
                Create project
              </button>
            </form>
          ) : null}
          {projectsQuery.isLoading ? (
            <p className="inline-flex items-center gap-2 text-xs text-graphite">
              <LoaderCircle size={14} className="animate-spin" /> Loading projects…
            </p>
          ) : projects.length === 0 ? (
            <p className="text-sm text-graphite">No projects yet.</p>
          ) : (
            <div className="grid gap-2">
              {projects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => onOpenLab()}
                  className="rounded-md border border-black/10 px-3 py-2 text-left hover:bg-black/5"
                >
                  <div className="text-sm font-medium text-ink">{project.name}</div>
                  <div className="mt-0.5 text-[11px] text-graphite">{project.status}</div>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-ink">Recent experiments</h3>
          {experimentsQuery.isLoading ? (
            <p className="inline-flex items-center gap-2 text-xs text-graphite">
              <LoaderCircle size={14} className="animate-spin" /> Loading experiments…
            </p>
          ) : recentExperiments.length === 0 ? (
            <p className="text-sm text-graphite">No experiments in this workspace yet.</p>
          ) : (
            <div className="grid gap-2">
              {recentExperiments.map((experiment) => (
                <button
                  key={experiment.id}
                  type="button"
                  onClick={() => onOpenLab(experiment.id)}
                  className="rounded-md border border-black/10 px-3 py-2 text-left hover:bg-black/5"
                >
                  <div className="text-sm font-medium text-ink">{experiment.title}</div>
                  <div className="mt-0.5 text-[11px] text-graphite">
                    v{experiment.versionCount} · {experiment.updated}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
