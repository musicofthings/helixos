"use client";

import {
  Activity,
  Beaker,
  CheckCircle2,
  ClipboardList,
  Dna,
  FlaskConical,
  LoaderCircle,
  Network,
  PackagePlus,
  Play,
  Plus,
  Save,
  Search,
  ShieldCheck,
  TestTube2,
  ToggleLeft,
  ToggleRight
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentPanel } from "./agent/agent-panel";
import { CommandPalette, useCommandPaletteShortcut, type CommandPaletteItem } from "./shell/command-palette";
import {
  useAgentSession,
  useAuditEvents,
  useConnectors,
  useCreateExperiment,
  useExperiments,
  useOrganizations,
  useRunConnectorJob,
  useSequence,
  useUpdateExperimentStatus
} from "../hooks/use-helix-api";
import { useDesktopShell } from "../hooks/use-desktop-shell";
import { formatAuditEventMessage } from "../lib/audit-display";
import { canTransitionExperiment, type ExperimentViewModel } from "../lib/experiment-display";
import { getApiBaseUrl } from "../lib/api-config";

type View = "workspace" | "experiments" | "sequences" | "inventory" | "connectors";

type Reagent = {
  id: string;
  name: string;
  lot: string;
  stock: number;
  unit: string;
  expires: string;
  status: "OK" | "Low" | "Expiring" | "Out";
};

type ConnectorState = {
  id: string;
  name: string;
  scopes: string[];
  enabled: boolean;
  lastRun: string;
};

const initialInventory: Reagent[] = [
  { id: "RG-201", name: "Q5 polymerase", lot: "M0491X", stock: 7, unit: "tubes", expires: "2026-09-18", status: "OK" },
  { id: "RG-188", name: "Gibson master mix", lot: "GMM-44", stock: 2, unit: "vials", expires: "2026-06-02", status: "Low" },
  { id: "RG-144", name: "Ampicillin", lot: "AMP-9B", stock: 1, unit: "bottle", expires: "2026-05-29", status: "Expiring" }
];

type ActivityEvent = {
  id: string;
  message: string;
};

const workflow = ["Sample Received", "DNA Extraction", "QC", "Library Prep", "Sequencing", "Analysis", "Reporting"];

const navItems: Array<{ id: View; icon: LucideIcon; label: string }> = [
  { id: "workspace", icon: ClipboardList, label: "Workspace" },
  { id: "experiments", icon: FlaskConical, label: "Experiments" },
  { id: "sequences", icon: Dna, label: "Sequences" },
  { id: "inventory", icon: Beaker, label: "Inventory" },
  { id: "connectors", icon: Network, label: "Connectors" }
];

const defaultSequence =
  "ATGGCTAGCGGATCCATGACCATGATTACGCCAAGCTTGCATGCCTGCAGGTCGACTCTAGAGGATCCCCGGGTACCGAGCTCGAATTC";

function cleanDna(sequence: string) {
  return sequence.toUpperCase().replace(/[^ACGT]/g, "");
}

function gcPercent(sequence: string) {
  const clean = sequence.toUpperCase().replace(/[^ACGT]/g, "");
  if (!clean.length) return 0;
  const gc = clean.split("").filter((base) => base === "G" || base === "C").length;
  return Math.round((gc / clean.length) * 1000) / 10;
}

function findOrfs(sequence: string) {
  const clean = sequence.toUpperCase().replace(/[^ACGT]/g, "");
  const stops = new Set(["TAA", "TAG", "TGA"]);
  const orfs: Array<{ start: number; end: number; length: number }> = [];

  for (let frame = 0; frame < 3; frame += 1) {
    for (let index = frame; index < clean.length - 2; index += 3) {
      if (clean.slice(index, index + 3) !== "ATG") continue;
      for (let cursor = index + 3; cursor < clean.length - 2; cursor += 3) {
        if (stops.has(clean.slice(cursor, cursor + 3))) {
          orfs.push({ start: index + 1, end: cursor + 3, length: cursor + 3 - index });
          break;
        }
      }
    }
  }

  return orfs.sort((a, b) => b.length - a.length).slice(0, 4);
}

function todayStamp() {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short"
  }).format(new Date());
}

function nextReagentId(inventory: Reagent[]) {
  const highest = inventory.reduce((max, item) => {
    const match = item.id.match(/^RG-(\d+)$/);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 200);
  return `RG-${highest + 1}`;
}

function deriveReagentStatus(stock: number, expires: string): Reagent["status"] {
  if (stock <= 0) return "Out";
  if (stock <= 2) return "Low";

  const expiryTime = new Date(`${expires}T00:00:00`).getTime();
  if (!Number.isNaN(expiryTime)) {
    const daysUntilExpiry = (expiryTime - Date.now()) / 86_400_000;
    if (daysUntilExpiry <= 45) return "Expiring";
  }

  return "OK";
}

const DEMO_SEQUENCE_ID = "seq_demo_reporter";

export function WorkspaceApp({ initialDesktopShell = false }: { initialDesktopShell?: boolean }) {
  const { isDesktop, sidecarStatus, canRestartSidecar } = useDesktopShell(initialDesktopShell);
  const apiEnabled = !isDesktop || sidecarStatus === "ready";

  const organizationsQuery = useOrganizations(apiEnabled);
  const experimentsQuery = useExperiments(apiEnabled);
  const connectorsQuery = useConnectors(apiEnabled);

  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string | undefined>();
  const primaryOrganizationId = selectedOrganizationId ?? organizationsQuery.data?.[0]?.id;

  const createExperimentMutation = useCreateExperiment(primaryOrganizationId);
  const updateExperimentStatusMutation = useUpdateExperimentStatus(primaryOrganizationId);
  const runConnectorJobMutation = useRunConnectorJob(primaryOrganizationId);

  const auditEventsQuery = useAuditEvents(primaryOrganizationId, apiEnabled);
  const agentSession = useAgentSession(primaryOrganizationId, apiEnabled);
  const demoSequenceQuery = useSequence(DEMO_SEQUENCE_ID, apiEnabled && Boolean(primaryOrganizationId));

  const experiments = useMemo(() => experimentsQuery.data ?? [], [experimentsQuery.data]);
  const [activeView, setActiveView] = useState<View>("workspace");
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | undefined>();
  const [inventory, setInventory] = useState(initialInventory);
  const [connectorState, setConnectorState] = useState<Record<string, Pick<ConnectorState, "enabled" | "lastRun">>>({});
  const [workflowStep, setWorkflowStep] = useState(2);
  const [sequence, setSequence] = useState(defaultSequence);
  const [loadedSequenceName, setLoadedSequenceName] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftProject, setDraftProject] = useState("Cloning");
  const [draftBlock, setDraftBlock] = useState("Objective\nDesign and document the next wet-lab step.");
  const [activity, setActivity] = useState<ActivityEvent[]>([
    { id: "seed-1", message: "Workspace opened" }
  ]);
  const activityCounter = useRef(0);

  useEffect(() => {
    if (!selectedExperimentId && experiments.length > 0) {
      setSelectedExperimentId(experiments[0].id);
    }
  }, [experiments, selectedExperimentId]);

  const displayExperiments = experiments;

  const connectorRegistry = useMemo(() => connectorsQuery.data ?? [], [connectorsQuery.data]);
  const connectorTransportById = useMemo(
    () => new Map(connectorRegistry.map((connector) => [connector.id, connector.transport])),
    [connectorRegistry]
  );

  const selectedExperiment =
    displayExperiments.find((experiment) => experiment.id === selectedExperimentId) ??
    displayExperiments[0] ??
    null;

  const connectors: ConnectorState[] = useMemo(() => {
    return connectorRegistry.map((connector) => {
      const state = connectorState[connector.id];
      return {
        id: connector.id,
        name: connector.name,
        scopes: connector.scopes,
        enabled: state?.enabled ?? connector.enabled_by_default,
        lastRun: state?.lastRun ?? "Idle"
      };
    });
  }, [connectorRegistry, connectorState]);
  const cleanSequence = cleanDna(sequence);
  const sequenceStats = useMemo(
    () => ({
      length: cleanSequence.length,
      gc: gcPercent(cleanSequence),
      orfs: findOrfs(cleanSequence)
    }),
    [cleanSequence]
  );

  const filteredExperiments = displayExperiments.filter((experiment) =>
    [experiment.title, experiment.project, experiment.owner, experiment.status].join(" ").toLowerCase().includes(search.toLowerCase())
  );

  const auditTrailItems = useMemo(() => {
    const apiItems =
      auditEventsQuery.data?.map((event) => ({
        id: event.id,
        message: formatAuditEventMessage(event)
      })) ?? [];
    const localItems = activity.map((item) => ({ id: item.id, message: item.message }));
    const seen = new Set<string>();
    const merged = [];

    for (const item of [...apiItems, ...localItems]) {
      if (seen.has(item.id)) {
        continue;
      }
      seen.add(item.id);
      merged.push(item);
      if (merged.length >= 5) {
        break;
      }
    }

    return merged;
  }, [activity, auditEventsQuery.data]);

  function log(message: string) {
    activityCounter.current += 1;
    const id = `activity-${activityCounter.current}`;
    setActivity((items) => [{ id, message: `${todayStamp()} - ${message}` }, ...items].slice(0, 8));
  }

  function createExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draftTitle.trim() || !primaryOrganizationId) return;

    const blocks = draftBlock
      .split("\n")
      .map((block) => block.trim())
      .filter(Boolean);

    createExperimentMutation.mutate(
      {
        organizationId: primaryOrganizationId,
        title: draftTitle.trim(),
        projectId: draftProject.toLowerCase().replace(/\s+/g, "_"),
        blocks: blocks.length ? blocks : ["Untitled note"]
      },
      {
        onSuccess: (experiment) => {
          setSelectedExperimentId(experiment.id);
          setActiveView("experiments");
          setDraftTitle("");
          log(`Created ${experiment.id}`);
        },
        onError: (error) => {
          log(error instanceof Error ? error.message : "Failed to create experiment");
        }
      }
    );
  }

  function updateExperimentStatus(status: ExperimentViewModel["status"]) {
    if (!selectedExperiment) return;
    if (!canTransitionExperiment(selectedExperiment.status, status)) {
      log(`Blocked ${selectedExperiment.id} transition from ${selectedExperiment.status} to ${status}`);
      return;
    }

    updateExperimentStatusMutation.mutate(
      { experimentId: selectedExperiment.id, status },
      {
        onSuccess: (experiment) => {
          log(`${experiment.id} marked ${experiment.status}`);
        },
        onError: (error) => {
          log(error instanceof Error ? error.message : `Failed to update ${selectedExperiment.id}`);
        }
      }
    );
  }

  function consumeReagent(id: string) {
    const item = inventory.find((candidate) => candidate.id === id);
    if (!item || item.stock <= 0) {
      log(`Blocked reagent usage for ${id}`);
      return;
    }

    setInventory((items) =>
      items.map((item) => {
        if (item.id !== id) return item;
        const stock = Math.max(0, item.stock - 1);
        return { ...item, stock, status: deriveReagentStatus(stock, item.expires) };
      })
    );
    log(`Recorded reagent usage for ${id}`);
  }

  function addReagent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const lot = String(form.get("lot") ?? "").trim();
    const stock = Math.max(0, Number(form.get("stock") ?? 1) || 0);
    const expires = String(form.get("expires") ?? "2026-12-31");
    if (!name || !lot) return;
    setInventory((items) => [
      {
        id: nextReagentId(items),
        name,
        lot,
        stock,
        unit: "units",
        expires,
        status: deriveReagentStatus(stock, expires)
      },
      ...items
    ]);
    event.currentTarget.reset();
    log(`Added reagent ${name}`);
  }

  function toggleConnector(id: string) {
    const connector = connectors.find((item) => item.id === id);
    setConnectorState((items) => ({
      ...items,
      [id]: {
        enabled: !(items[id]?.enabled ?? connector?.enabled ?? false),
        lastRun: items[id]?.lastRun ?? connector?.lastRun ?? "Idle"
      }
    }));
    log(`${connector?.enabled ? "Disabled" : "Enabled"} connector ${id}`);
  }

  const runConnector = useCallback(
    (id: string) => {
      const connector = connectors.find((item) => item.id === id);
      if (!connector?.enabled) {
        log(`Blocked disabled connector ${id}`);
        return;
      }

      const transport = connectorTransportById.get(id);
      if (transport === "stdio" && !isDesktop) {
        log(`${id} requires the desktop shell and MCP bridge`);
        return;
      }

      if (id === "biopython-local") {
        runConnectorJobMutation.mutate(
          {
            connectorId: id,
            tool: "analyze_sequence",
            arguments: { sequence: cleanSequence }
          },
          {
            onSuccess: (result) => {
              const summary =
                result.result && typeof result.result === "object" && "length" in (result.result as object)
                  ? `${String((result.result as { length: unknown }).length)} bp · ${String((result.result as { gc_percent?: unknown }).gc_percent ?? "?")}% GC`
                  : "completed";
              setConnectorState((items) => ({
                ...items,
                [id]: { enabled: true, lastRun: summary }
              }));
              log(`Ran ${id} analyze_sequence (${summary})`);
            },
            onError: (error) => {
              const message = error instanceof Error ? error.message : `Failed to run connector ${id}`;
              setConnectorState((items) => ({
                ...items,
                [id]: { enabled: true, lastRun: "Failed" }
              }));
              log(message);
            }
          }
        );
        return;
      }

      log(`${id} is registered but remote dispatch is not configured yet`);
    },
    [cleanSequence, connectorTransportById, connectors, isDesktop, runConnectorJobMutation]
  );

  const runAgentQuickPrompt = useCallback(() => {
    setActiveView("workspace");
    log("Open the lab agent panel to run a quick prompt");
  }, []);

  const commandItems = useMemo<CommandPaletteItem[]>(
    () => [
      { id: "nav-workspace", label: "Go to workspace", group: "Navigate", run: () => setActiveView("workspace") },
      { id: "nav-experiments", label: "Go to experiments", group: "Navigate", run: () => setActiveView("experiments") },
      { id: "nav-sequences", label: "Go to sequences", group: "Navigate", run: () => setActiveView("sequences") },
      { id: "nav-inventory", label: "Go to inventory", group: "Navigate", run: () => setActiveView("inventory") },
      { id: "nav-connectors", label: "Go to connectors", group: "Navigate", run: () => setActiveView("connectors") },
      {
        id: "create-experiment",
        label: "Create new experiment",
        group: "Lab",
        keywords: ["draft", "eln"],
        run: () => setActiveView("experiments")
      },
      {
        id: "analyze-sequence",
        label: "Analyze current sequence with BioPython Local",
        group: "Connectors",
        keywords: ["mcp", "biopython", "sequence"],
        disabled: !isDesktop || !connectors.some((connector) => connector.id === "biopython-local" && connector.enabled),
        run: () => runConnector("biopython-local")
      },
      {
        id: "agent-prompt",
        label: "Open lab agent quick prompt",
        group: "Agent",
        keywords: ["copilot", "ai"],
        run: runAgentQuickPrompt
      },
      {
        id: "restart-sidecar",
        label: "Restart desktop API sidecar",
        group: "Desktop",
        disabled: !canRestartSidecar,
        run: async () => {
          if (!window.helixDesktopActions) {
            return;
          }
          await window.helixDesktopActions.restartSidecar();
          log("Restarted desktop API sidecar");
        }
      }
    ],
    [canRestartSidecar, connectors, isDesktop, runAgentQuickPrompt, runConnector]
  );

  useCommandPaletteShortcut(() => setCommandPaletteOpen(true));

  const apiStatusMessage = organizationsQuery.error
    ? isDesktop
      ? "API sidecar unavailable. Restart the desktop shell or run npm run dev:desktop."
      : `API unavailable at ${getApiBaseUrl()}. Run npm run dev:api or npm run dev:browser.`
    : experimentsQuery.error
      ? "Failed to load experiments from the API."
      : null;

  return (
    <main className="min-h-screen bg-[#f7f8f5]">
      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} items={commandItems} />
      <div className="mx-auto grid min-h-screen max-w-7xl lg:grid-cols-[270px_1fr]">
        <aside className="border-r border-black/10 bg-[#f1f4ef] px-5 py-6">
          <div className="text-xl font-semibold text-ink">HelixOS</div>
          <div className="mt-1 text-sm text-graphite">Laboratory operating system</div>

          <nav className="mt-8 grid gap-1 text-sm">
            {navItems.map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                onClick={() => setActiveView(id)}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-left transition ${
                  activeView === id ? "bg-white text-fern shadow-sm" : "text-ink hover:bg-black/5"
                }`}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </nav>

          <section className="mt-8 rounded-md border border-black/10 bg-white p-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-ink">
              <ShieldCheck size={16} />
              Audit trail
            </div>
            <div className="mt-3 grid gap-2 text-xs text-graphite">
              {auditTrailItems.map((item) => (
                <div key={item.id} className="border-l-2 border-fern/30 pl-2">
                  {item.message}
                </div>
              ))}
            </div>
          </section>
        </aside>

        <section className="px-5 py-6 lg:px-8">
          <header className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-ink">AI-native molecular biology workspace</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-graphite">
                Create records, analyze sequences, mutate inventory, run connector jobs, and move diagnostic workflow state from one working surface.
              </p>
              {apiStatusMessage ? (
                <p className="mt-2 rounded-md border border-signal/30 bg-[#eef6f7] px-3 py-2 text-xs text-signal">{apiStatusMessage}</p>
              ) : null}
              {isDesktop ? (
                <p className="mt-2 inline-flex items-center gap-2 rounded-md border border-fern/20 bg-[#edf5ef] px-3 py-1 text-xs text-fern">
                  Desktop shell · API sidecar {sidecarStatus ?? "ready"}
                </p>
              ) : null}
              {organizationsQuery.data && organizationsQuery.data.length > 1 ? (
                <label className="mt-2 flex items-center gap-2 text-xs text-graphite">
                  Organization
                  <select
                    value={primaryOrganizationId ?? ""}
                    onChange={(event) => setSelectedOrganizationId(event.target.value)}
                    className="rounded-md border border-black/10 bg-white px-2 py-1 text-xs text-ink outline-none focus:border-fern"
                  >
                    {organizationsQuery.data.map((organization) => (
                      <option key={organization.id} value={organization.id}>
                        {organization.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              {organizationsQuery.isLoading || experimentsQuery.isLoading || agentSession.isPending ? (
                <p className="mt-2 inline-flex items-center gap-2 text-xs text-graphite">
                  <LoaderCircle size={14} className="animate-spin" />
                  Syncing workspace data...
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setCommandPaletteOpen(true)}
              className="inline-flex items-center gap-2 rounded-md border border-black/10 px-4 py-2 text-sm font-medium hover:bg-black/5"
            >
              <Search size={16} />
              Command
              <kbd className="rounded border border-black/10 px-1.5 py-0.5 text-[10px] text-graphite">⌘K</kbd>
            </button>
            <button
              onClick={() => setActiveView("experiments")}
              className="inline-flex items-center gap-2 rounded-md bg-fern px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#1d513c]"
            >
              <Plus size={16} />
              New experiment
            </button>
            </div>
          </header>

          {activeView === "workspace" && (
            <div className="mt-6 grid gap-4">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Metric icon={FlaskConical} label="Open experiments" value={String(displayExperiments.length)} />
                <Metric icon={Dna} label="Sequence length" value={`${sequenceStats.length} bp`} />
                <Metric icon={TestTube2} label="Low stock items" value={String(inventory.filter((item) => item.status !== "OK").length)} />
                <Metric icon={Network} label="Enabled connectors" value={String(connectors.filter((item) => item.enabled).length)} />
              </div>

              <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Diagnostic workflow</h2>
                  <button
                    onClick={() => {
                      setWorkflowStep((step) => {
                        const nextStep = Math.min(workflow.length - 1, step + 1);
                        if (nextStep !== step) {
                          log(`Workflow advanced to ${workflow[nextStep]}`);
                        }
                        return nextStep;
                      });
                    }}
                    disabled={workflowStep === workflow.length - 1}
                    className="inline-flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5 disabled:text-black/40"
                  >
                    <Play size={14} />
                    Advance
                  </button>
                </div>
                <div className="grid gap-2 md:grid-cols-7">
                  {workflow.map((step, index) => (
                    <button
                      key={step}
                      onClick={() => {
                        setWorkflowStep(index);
                        log(`Workflow set to ${step}`);
                      }}
                      className={`min-h-20 rounded-md border p-3 text-left transition ${
                        index === workflowStep
                          ? "border-fern bg-[#edf5ef]"
                          : index < workflowStep
                            ? "border-signal/30 bg-[#eef6f7]"
                            : "border-black/10 bg-[#fbfbf8]"
                      }`}
                    >
                      <div className="text-xs font-medium text-signal">0{index + 1}</div>
                      <div className="mt-2 text-sm font-medium text-ink">{step}</div>
                    </button>
                  ))}
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                {selectedExperiment ? (
                  <ExperimentPanel
                    experiment={selectedExperiment}
                    onReview={() => updateExperimentStatus("In review")}
                    onSign={() => updateExperimentStatus("Signed")}
                  />
                ) : (
                  <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
                    <h2 className="text-sm font-semibold text-ink">No experiments yet</h2>
                    <p className="mt-2 text-sm text-graphite">Create a draft experiment to populate the workspace.</p>
                  </section>
                )}
                <AgentPanel
                  organizationId={primaryOrganizationId}
                  sessionId={agentSession.sessionId}
                  context={{
                    experiment_id: selectedExperiment?.id,
                    experiment_title: selectedExperiment?.title,
                    sequence_length: sequenceStats.length
                  }}
                  onActivity={log}
                />
              </div>
            </div>
          )}

          {activeView === "experiments" && (
            <div className="mt-6 grid gap-4 xl:grid-cols-[360px_1fr]">
              <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-ink">Create experiment</h2>
                <form onSubmit={createExperiment} className="mt-4 grid gap-3">
                  <label htmlFor="experiment-title" className="grid gap-1 text-xs font-medium text-graphite">
                    Title
                    <input
                      id="experiment-title"
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-fern"
                      placeholder="e.g. Golden Gate assembly"
                    />
                  </label>
                  <label htmlFor="experiment-project" className="grid gap-1 text-xs font-medium text-graphite">
                    Project
                    <select
                      id="experiment-project"
                      value={draftProject}
                      onChange={(event) => setDraftProject(event.target.value)}
                      className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-fern"
                    >
                      <option>Cloning</option>
                      <option>Diagnostics</option>
                      <option>Biobank</option>
                      <option>Assay Development</option>
                    </select>
                  </label>
                  <label htmlFor="experiment-blocks" className="grid gap-1 text-xs font-medium text-graphite">
                    Initial blocks
                    <textarea
                      id="experiment-blocks"
                      value={draftBlock}
                      onChange={(event) => setDraftBlock(event.target.value)}
                      rows={6}
                      className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-fern"
                    />
                  </label>
                  <button
                    disabled={!draftTitle.trim() || !primaryOrganizationId || createExperimentMutation.isPending}
                    className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-4 py-2 text-sm font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
                  >
                    {createExperimentMutation.isPending ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}
                    Save draft
                  </button>
                </form>
              </section>

              <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Experiment records</h2>
                  <label className="flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-sm text-graphite">
                    <Search size={15} />
                    <input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search records"
                      className="w-40 bg-transparent outline-none"
                    />
                  </label>
                </div>
                <div className="mt-4 grid gap-2">
                  {filteredExperiments.length ? (
                    filteredExperiments.map((experiment) => (
                      <button
                        key={experiment.id}
                        onClick={() => setSelectedExperimentId(experiment.id)}
                        className={`rounded-md border p-3 text-left transition ${
                          selectedExperiment && experiment.id === selectedExperiment.id
                            ? "border-fern bg-[#edf5ef]"
                            : "border-black/10 hover:bg-black/5"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-semibold text-ink">{experiment.title}</div>
                          <span className="rounded-md bg-[#eef1ed] px-2 py-1 text-xs text-graphite">{experiment.status}</span>
                        </div>
                        <div className="mt-2 text-xs text-graphite">
                          {experiment.id} · {experiment.project} · {experiment.owner} · {experiment.updated}
                        </div>
                      </button>
                    ))
                  ) : (
                    <div className="rounded-md border border-black/10 bg-[#fbfbf8] p-4 text-sm text-graphite">
                      No experiment records yet. Create one using the form on the left.
                    </div>
                  )}
                </div>
              </section>
            </div>
          )}

          {activeView === "sequences" && (
            <section className="mt-6 rounded-md border border-black/10 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-ink">Sequence analyzer</h2>
                  {loadedSequenceName ? (
                    <p className="mt-1 text-xs text-graphite">
                      Loaded from API: {loadedSequenceName}
                      {demoSequenceQuery.data ? ` · ${demoSequenceQuery.data.length} bp metadata · ${demoSequenceQuery.data.topology}` : ""}
                    </p>
                  ) : null}
                </div>
                <button
                  onClick={() => {
                    setSequence(defaultSequence);
                    setLoadedSequenceName(demoSequenceQuery.data?.name ?? DEMO_SEQUENCE_ID);
                    log(`Loaded demo sequence ${DEMO_SEQUENCE_ID} from API`);
                  }}
                  disabled={demoSequenceQuery.isLoading}
                  className="rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5"
                >
                  {demoSequenceQuery.isLoading ? "Loading demo..." : "Load demo sequence"}
                </button>
              </div>
              {demoSequenceQuery.data?.features.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {demoSequenceQuery.data.features.map((feature) => (
                    <span key={`${feature.name}-${feature.start}`} className="rounded-md bg-[#eef1ed] px-2 py-1 text-xs text-graphite">
                      {feature.name} ({feature.start}-{feature.end})
                    </span>
                  ))}
                </div>
              ) : null}
              <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_340px]">
                <textarea
                  aria-label="DNA sequence"
                  value={sequence}
                  onChange={(event) => setSequence(event.target.value)}
                  rows={12}
                  className="rounded-md border border-black/10 bg-[#fbfbf8] p-3 font-mono text-sm text-ink outline-none focus:border-fern"
                />
                <div className="grid gap-3">
                  <Metric icon={Dna} label="Length" value={`${sequenceStats.length} bp`} />
                  <Metric icon={Activity} label="GC content" value={`${sequenceStats.gc}%`} />
                  <div className="rounded-md border border-black/10 bg-[#fbfbf8] p-4">
                    <div className="text-sm font-semibold text-ink">Detected ORFs</div>
                    <div className="mt-3 grid gap-2 text-xs text-graphite">
                      {sequenceStats.orfs.length ? (
                        sequenceStats.orfs.map((orf) => (
                          <div key={`${orf.start}-${orf.end}`} className="rounded-md bg-white px-3 py-2">
                            {orf.start}-{orf.end} · {orf.length} bp
                          </div>
                        ))
                      ) : (
                        <div>No complete ORF detected in current frame scan.</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {activeView === "inventory" && (
            <div className="mt-6 grid gap-4 xl:grid-cols-[360px_1fr]">
              <p className="xl:col-span-2 rounded-md border border-black/10 bg-[#fbfbf8] px-3 py-2 text-xs text-graphite">
                Inventory is a local prototype. Changes are not persisted or audited until the inventory module is implemented.
              </p>
              <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-ink">Add reagent</h2>
                <form onSubmit={addReagent} className="mt-4 grid gap-3">
                  <input name="name" required aria-label="Reagent name" placeholder="Reagent name" className="rounded-md border border-black/10 px-3 py-2 text-sm outline-none focus:border-fern" />
                  <input name="lot" required aria-label="Reagent lot" placeholder="Lot" className="rounded-md border border-black/10 px-3 py-2 text-sm outline-none focus:border-fern" />
                  <input name="stock" aria-label="Reagent stock" type="number" min="1" defaultValue="1" className="rounded-md border border-black/10 px-3 py-2 text-sm outline-none focus:border-fern" />
                  <input name="expires" aria-label="Reagent expiry date" type="date" defaultValue="2026-12-31" className="rounded-md border border-black/10 px-3 py-2 text-sm outline-none focus:border-fern" />
                  <button className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-4 py-2 text-sm font-medium text-white hover:bg-[#1d513c]">
                    <PackagePlus size={16} />
                    Add item
                  </button>
                </form>
              </section>
              <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-ink">Reagent catalog</h2>
                <div className="mt-4 grid gap-2">
                  {inventory.map((item) => (
                    <div key={item.id} className="grid gap-3 rounded-md border border-black/10 p-3 md:grid-cols-[1fr_auto] md:items-center">
                      <div>
                        <div className="text-sm font-semibold text-ink">{item.name}</div>
                        <div className="mt-1 text-xs text-graphite">
                          {item.id} · lot {item.lot} · expires {item.expires}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium text-ink">
                          {item.stock} {item.unit}
                        </span>
                        <span className="rounded-md bg-[#eef1ed] px-2 py-1 text-xs text-graphite">{item.status}</span>
                        <button
                          onClick={() => consumeReagent(item.id)}
                          disabled={item.stock <= 0}
                          className="rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5 disabled:text-black/40"
                        >
                          Use 1
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

          {activeView === "connectors" && (
            <section className="mt-6 rounded-md border border-black/10 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-ink">MCP connector registry</h2>
              {!isDesktop ? (
                <p className="mt-2 rounded-md border border-black/10 bg-[#fbfbf8] px-3 py-2 text-xs text-graphite">
                  Stdio connectors such as BioPython Local require the desktop shell (`npm run dev:desktop`) with the MCP bridge on port 8766.
                </p>
              ) : null}
              <div className="mt-4 grid gap-3">
                {connectors.map((connector) => {
                  const transport = connectorTransportById.get(connector.id);
                  const requiresDesktop = transport === "stdio";
                  const canRun = connector.enabled && (!requiresDesktop || isDesktop) && connector.id === "biopython-local";

                  return (
                  <div key={connector.id} className="grid gap-3 rounded-md border border-black/10 p-4 md:grid-cols-[1fr_auto] md:items-center">
                    <div>
                      <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                        {connector.enabled ? <CheckCircle2 size={16} className="text-fern" /> : <Network size={16} className="text-graphite" />}
                        {connector.name}
                        {requiresDesktop ? (
                          <span className="rounded-md bg-[#eef1ed] px-2 py-0.5 text-[10px] font-medium uppercase text-graphite">Desktop</span>
                        ) : null}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {connector.scopes.map((scope) => (
                          <span key={scope} className="rounded-md bg-[#eef1ed] px-2 py-1 text-xs text-graphite">
                            {scope}
                          </span>
                        ))}
                      </div>
                      <div className="mt-2 text-xs text-graphite">Last run: {connector.lastRun}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => toggleConnector(connector.id)} className="rounded-md border border-black/10 p-2 hover:bg-black/5" aria-label={`Toggle ${connector.name}`}>
                        {connector.enabled ? <ToggleRight size={24} className="text-fern" /> : <ToggleLeft size={24} className="text-graphite" />}
                      </button>
                      <button
                        onClick={() => runConnector(connector.id)}
                        disabled={!canRun || runConnectorJobMutation.isPending}
                        className="inline-flex items-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:bg-black/20"
                      >
                        <Play size={14} />
                        Run
                      </button>
                    </div>
                  </div>
                  );
                })}
              </div>
            </section>
          )}
        </section>
      </div>
    </main>
  );
}

function Metric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-medium uppercase text-graphite">{label}</div>
        <Icon size={17} className="text-fern" />
      </div>
      <div className="mt-3 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}

function ExperimentPanel({
  experiment,
  onReview,
  onSign
}: {
  experiment: ExperimentViewModel;
  onReview: () => void;
  onSign: () => void;
}) {
  const canSendReview = canTransitionExperiment(experiment.status, "In review");
  const canSign = canTransitionExperiment(experiment.status, "Signed");

  return (
    <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">{experiment.title}</h2>
          <div className="mt-1 text-xs text-graphite">
            {experiment.id} · {experiment.project} · {experiment.status}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onReview}
            disabled={!canSendReview}
            className="rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5 disabled:cursor-not-allowed disabled:bg-black/5 disabled:text-black/40"
          >
            Send review
          </button>
          <button
            onClick={onSign}
            disabled={!canSign}
            className="rounded-md bg-fern px-3 py-2 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
          >
            Sign
          </button>
        </div>
      </div>
      <div className="mt-4 grid gap-2">
        {experiment.blocks.map((block) => (
          <div key={block} className="rounded-md border border-black/10 bg-[#fbfbf8] px-3 py-2 text-sm text-ink">
            {block}
          </div>
        ))}
      </div>
    </section>
  );
}
