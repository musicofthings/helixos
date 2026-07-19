"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { LoaderCircle, Plus, Trash2 } from "lucide-react";
import type { Protocol, ProtocolStep, Workspace } from "@helixos/types";

import {
  useCreateProtocol,
  useDeleteProtocol,
  useImportProtocol,
  useProtocols,
  useUpdateProtocol
} from "../../hooks/use-helix-api";

export function ProtocolsView({
  organizationId,
  workspace,
  apiEnabled,
  onActivity
}: {
  organizationId?: string;
  workspace?: Workspace | null;
  apiEnabled: boolean;
  onActivity: (message: string) => void;
}) {
  const workspaceId = workspace?.id;
  const protocolsQuery = useProtocols(
    { organizationId, workspaceId },
    apiEnabled && Boolean(workspaceId)
  );
  const createProtocol = useCreateProtocol(organizationId);
  const updateProtocol = useUpdateProtocol(organizationId, workspaceId);
  const deleteProtocol = useDeleteProtocol(organizationId, workspaceId);
  const importProtocol = useImportProtocol(organizationId, workspaceId);

  const protocols = protocolsQuery.data ?? [];
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [mode, setMode] = useState<"view" | "create" | "import">("view");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [stepsText, setStepsText] = useState("1. Title\nBody for step 1");
  const [importUrl, setImportUrl] = useState("");
  const [importProvider, setImportProvider] = useState<"protocols_io" | "url">("protocols_io");
  const [deleteTarget, setDeleteTarget] = useState<Protocol | null>(null);

  const selected = protocols.find((protocol) => protocol.id === selectedId) ?? null;

  useEffect(() => {
    if (!selected && protocols[0]) {
      setSelectedId(protocols[0].id);
    }
    if (selectedId && !protocols.some((protocol) => protocol.id === selectedId)) {
      setSelectedId(protocols[0]?.id);
    }
  }, [protocols, selected, selectedId]);

  // Hydrate the edit form only when the selected protocol id (or mode) changes,
  // not on every react-query refetch of the same protocol object identity.
  const hydratedProtocolId = useRef<string | undefined>();
  useEffect(() => {
    if (mode !== "view") {
      hydratedProtocolId.current = undefined;
      return;
    }
    if (!selected) return;
    if (hydratedProtocolId.current === selected.id) return;
    hydratedProtocolId.current = selected.id;
    setName(selected.name);
    setDescription(selected.description ?? "");
    setStepsText(serializeSteps(selected.steps));
  }, [selected, mode]);

  if (!workspace) {
    return (
      <div className="mt-6 rounded-md border border-dashed border-black/15 bg-white p-8 text-center shadow-sm">
        <h2 className="text-sm font-semibold text-ink">Select a workspace</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-graphite">
          Protocols live in the active workspace library. Choose a workspace channel in the sidebar
          first.
        </p>
      </div>
    );
  }

  function startCreate() {
    setMode("create");
    setName("");
    setDescription("");
    setStepsText("1. Title\nBody for step 1");
  }

  function startImport() {
    setMode("import");
    setImportUrl("");
    setImportProvider("protocols_io");
    setName("");
  }

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organizationId || !workspaceId || !name.trim()) return;
    createProtocol.mutate(
      {
        organizationId,
        workspaceId,
        name: name.trim(),
        description: description.trim() || undefined,
        steps: parseSteps(stepsText)
      },
      {
        onSuccess: (protocol) => {
          onActivity(`Created protocol ${protocol.name}`);
          setSelectedId(protocol.id);
          setMode("view");
        },
        onError: (error) =>
          onActivity(error instanceof Error ? error.message : "Failed to create protocol")
      }
    );
  }

  function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !name.trim()) return;
    updateProtocol.mutate(
      {
        protocolId: selected.id,
        name: name.trim(),
        description: description.trim() || null,
        steps: parseSteps(stepsText)
      },
      {
        onSuccess: (protocol) => onActivity(`Updated protocol ${protocol.name}`),
        onError: (error) =>
          onActivity(error instanceof Error ? error.message : "Failed to update protocol")
      }
    );
  }

  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organizationId || !workspaceId || !importUrl.trim()) return;
    importProtocol.mutate(
      {
        organizationId,
        workspaceId,
        sourceProvider: importProvider,
        sourceUrl: importUrl.trim(),
        name: name.trim() || undefined
      },
      {
        onSuccess: (protocol) => {
          onActivity(`Imported protocol stub ${protocol.name}`);
          setSelectedId(protocol.id);
          setMode("view");
        },
        onError: (error) =>
          onActivity(error instanceof Error ? error.message : "Failed to import protocol")
      }
    );
  }

  return (
    <div className="mt-6 grid gap-4 xl:grid-cols-[280px_1fr]">
      <section className="rounded-md border border-black/10 bg-white p-3 shadow-sm">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-graphite">Protocols</h2>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={startCreate}
              aria-label="Create protocol"
              title="Create protocol"
              className="rounded-md border border-black/10 p-1 text-graphite hover:bg-black/5"
            >
              <Plus size={14} />
            </button>
          </div>
        </div>
        <div className="mb-2 flex flex-wrap gap-1">
          <button
            type="button"
            onClick={startCreate}
            className="rounded-md border border-black/10 px-2 py-1 text-[11px] font-medium hover:bg-black/5"
          >
            New
          </button>
          <button
            type="button"
            onClick={startImport}
            className="rounded-md border border-black/10 px-2 py-1 text-[11px] font-medium hover:bg-black/5"
          >
            Import
          </button>
        </div>
        {protocolsQuery.isLoading ? (
          <p className="inline-flex items-center gap-2 text-xs text-graphite">
            <LoaderCircle size={14} className="animate-spin" /> Loading…
          </p>
        ) : protocols.length === 0 ? (
          <p className="text-xs text-graphite">No protocols yet.</p>
        ) : (
          <div className="grid gap-1.5">
            {protocols.map((protocol) => (
              <button
                key={protocol.id}
                type="button"
                onClick={() => {
                  setSelectedId(protocol.id);
                  setMode("view");
                }}
                className={`rounded-md border px-2.5 py-2 text-left ${
                  protocol.id === selectedId && mode === "view"
                    ? "border-fern bg-[#edf5ef]"
                    : "border-black/10 hover:bg-black/5"
                }`}
              >
                <div className="truncate text-sm font-medium text-ink">{protocol.name}</div>
                <div className="mt-0.5 truncate text-[11px] text-graphite">
                  {protocol.status} · {protocol.source_provider}
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
        {mode === "create" ? (
          <form onSubmit={submitCreate} className="grid gap-3">
            <h2 className="text-sm font-semibold text-ink">Create protocol</h2>
            <ProtocolFields
              name={name}
              description={description}
              stepsText={stepsText}
              onNameChange={setName}
              onDescriptionChange={setDescription}
              onStepsChange={setStepsText}
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={createProtocol.isPending || !name.trim()}
                className="rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:opacity-60"
              >
                {createProtocol.isPending ? "Creating…" : "Create protocol"}
              </button>
              <button
                type="button"
                onClick={() => setMode("view")}
                className="rounded-md border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-black/5"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : mode === "import" ? (
          <form onSubmit={submitImport} className="grid gap-3">
            <h2 className="text-sm font-semibold text-ink">Import protocol</h2>
            <p className="text-xs text-graphite">
              Creates a draft shell with source metadata. Live fetch from protocols.io / URL is not
              wired yet — edit steps after import.
            </p>
            <label className="grid gap-1 text-xs text-graphite">
              Source
              <select
                value={importProvider}
                onChange={(event) =>
                  setImportProvider(event.target.value as "protocols_io" | "url")
                }
                className="rounded-md border border-black/10 px-2 py-1.5 text-sm text-ink outline-none focus:border-fern"
              >
                <option value="protocols_io">protocols.io</option>
                <option value="url">Other URL</option>
              </select>
            </label>
            <input
              value={importUrl}
              onChange={(event) => setImportUrl(event.target.value)}
              placeholder={
                importProvider === "protocols_io"
                  ? "https://www.protocols.io/view/…"
                  : "https://…"
              }
              className="rounded-md border border-black/10 px-2 py-1.5 text-sm outline-none focus:border-fern"
              required
            />
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Optional display name"
              className="rounded-md border border-black/10 px-2 py-1.5 text-sm outline-none focus:border-fern"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={importProtocol.isPending || !importUrl.trim()}
                className="rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:opacity-60"
              >
                {importProtocol.isPending ? "Importing…" : "Import stub"}
              </button>
              <button
                type="button"
                onClick={() => setMode("view")}
                className="rounded-md border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-black/5"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : selected ? (
          <form onSubmit={submitEdit} className="grid gap-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 className="text-sm font-semibold text-ink">Edit protocol</h2>
              <button
                type="button"
                onClick={() => setDeleteTarget(selected)}
                className="inline-flex items-center gap-1 rounded-md border border-black/10 px-2 py-1 text-[11px] font-medium text-red-700 hover:bg-red-50"
              >
                <Trash2 size={12} />
                Delete
              </button>
            </div>
            <ProtocolFields
              name={name}
              description={description}
              stepsText={stepsText}
              onNameChange={setName}
              onDescriptionChange={setDescription}
              onStepsChange={setStepsText}
            />
            <p className="text-[11px] text-graphite">
              Status: {selected.status}
              {selected.source_url ? ` · source ${selected.source_url}` : ""}
            </p>
            <button
              type="submit"
              disabled={updateProtocol.isPending || !name.trim()}
              className="inline-flex w-fit rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:opacity-60"
            >
              {updateProtocol.isPending ? "Saving…" : "Save changes"}
            </button>
          </form>
        ) : (
          <div className="py-8 text-center">
            <h2 className="text-sm font-semibold text-ink">No protocol selected</h2>
            <p className="mt-2 text-sm text-graphite">Create or import a protocol to get started.</p>
          </div>
        )}
      </section>

      {deleteTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-md border border-black/10 bg-white p-4 shadow-lg">
            <h3 className="text-sm font-semibold text-ink">Delete protocol?</h3>
            <p className="mt-2 text-sm text-graphite">
              This permanently removes <span className="font-medium text-ink">{deleteTarget.name}</span>.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="rounded-md border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-black/5"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteProtocol.isPending}
                onClick={() =>
                  deleteProtocol.mutate(deleteTarget.id, {
                    onSuccess: () => {
                      onActivity(`Deleted protocol ${deleteTarget.name}`);
                      setDeleteTarget(null);
                    },
                    onError: (error) =>
                      onActivity(
                        error instanceof Error ? error.message : "Failed to delete protocol"
                      )
                  })
                }
                className="rounded-md bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-800 disabled:opacity-60"
              >
                {deleteProtocol.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ProtocolFields({
  name,
  description,
  stepsText,
  onNameChange,
  onDescriptionChange,
  onStepsChange
}: {
  name: string;
  description: string;
  stepsText: string;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onStepsChange: (value: string) => void;
}) {
  return (
    <>
      <input
        value={name}
        onChange={(event) => onNameChange(event.target.value)}
        placeholder="Protocol name"
        className="rounded-md border border-black/10 px-2 py-1.5 text-sm outline-none focus:border-fern"
        required
      />
      <textarea
        value={description}
        onChange={(event) => onDescriptionChange(event.target.value)}
        placeholder="Description (optional)"
        rows={2}
        className="rounded-md border border-black/10 px-2 py-1.5 text-sm outline-none focus:border-fern"
      />
      <label className="grid gap-1 text-xs text-graphite">
        Steps (numbered blocks; blank line starts a new step body continuation)
        <textarea
          value={stepsText}
          onChange={(event) => onStepsChange(event.target.value)}
          rows={10}
          className="rounded-md border border-black/10 px-2 py-1.5 font-mono text-sm text-ink outline-none focus:border-fern"
        />
      </label>
    </>
  );
}

function parseSteps(text: string): ProtocolStep[] {
  const lines = text.split("\n");
  const steps: ProtocolStep[] = [];
  let current: ProtocolStep | null = null;

  for (const line of lines) {
    const match = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (match) {
      if (current) steps.push(current);
      current = {
        order: Number(match[1]),
        title: match[2].trim() || `Step ${match[1]}`,
        body: ""
      };
      continue;
    }
    if (!current) {
      if (!line.trim()) continue;
      current = { order: 1, title: "Step 1", body: line };
      continue;
    }
    current.body = current.body ? `${current.body}\n${line}` : line;
  }
  if (current) steps.push(current);
  return steps.map((step, index) => ({ ...step, order: index + 1, body: step.body.trim() }));
}

function serializeSteps(steps: ProtocolStep[]): string {
  if (!steps.length) return "1. Title\nBody for step 1";
  return steps
    .slice()
    .sort((a, b) => a.order - b.order)
    .map((step) => `${step.order}. ${step.title}${step.body ? `\n${step.body}` : ""}`)
    .join("\n\n");
}
