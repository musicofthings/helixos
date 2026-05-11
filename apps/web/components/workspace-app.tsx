"use client";

import {
  Activity,
  Beaker,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  Dna,
  FlaskConical,
  History,
  Network,
  PackagePlus,
  Play,
  Plus,
  Save,
  Search,
  ShieldCheck,
  TestTube2,
  ToggleLeft,
  ToggleRight,
  Wand2
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { FormEvent, useMemo, useRef, useState } from "react";

type View = "workspace" | "experiments" | "sequences" | "inventory" | "connectors";

type Experiment = {
  id: string;
  title: string;
  project: string;
  owner: string;
  status: "Draft" | "In review" | "Signed";
  updated: string;
  blocks: string[];
};

type Reagent = {
  id: string;
  name: string;
  lot: string;
  stock: number;
  unit: string;
  expires: string;
  status: "OK" | "Low" | "Expiring" | "Out";
};

type Connector = {
  id: string;
  name: string;
  scopes: string[];
  enabled: boolean;
  lastRun: string;
};

type ActivityEvent = {
  id: string;
  message: string;
};

const initialExperiments: Experiment[] = [
  {
    id: "EXP-1042",
    title: "Gibson assembly of reporter plasmid",
    project: "Cloning",
    owner: "Dr. Rao",
    status: "Draft",
    updated: "Today 09:20",
    blocks: ["Assembly plan", "Vector backbone", "Reporter insert"]
  },
  {
    id: "EXP-1038",
    title: "Library prep QC for lung panel",
    project: "Diagnostics",
    owner: "Meera",
    status: "In review",
    updated: "Yesterday 17:42",
    blocks: ["Qubit results", "TapeStation trace", "Reviewer notes"]
  }
];

const initialInventory: Reagent[] = [
  { id: "RG-201", name: "Q5 polymerase", lot: "M0491X", stock: 7, unit: "tubes", expires: "2026-09-18", status: "OK" },
  { id: "RG-188", name: "Gibson master mix", lot: "GMM-44", stock: 2, unit: "vials", expires: "2026-06-02", status: "Low" },
  { id: "RG-144", name: "Ampicillin", lot: "AMP-9B", stock: 1, unit: "bottle", expires: "2026-05-29", status: "Expiring" }
];

const initialConnectors: Connector[] = [
  { id: "biopython-local", name: "BioPython Local", scopes: ["sequence:read", "sequence:analyze"], enabled: true, lastRun: "Idle" },
  { id: "pubmed", name: "PubMed", scopes: ["literature:search"], enabled: false, lastRun: "Never" },
  { id: "blast", name: "BLAST", scopes: ["sequence:search", "job:run"], enabled: false, lastRun: "Never" }
];

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

function nextExperimentId(experiments: Experiment[]) {
  const highest = experiments.reduce((max, experiment) => {
    const match = experiment.id.match(/^EXP-(\d+)$/);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 1000);
  return `EXP-${highest + 1}`;
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

function canTransitionExperiment(from: Experiment["status"], to: Experiment["status"]) {
  if (from === to) return false;
  if (from === "Signed") return false;
  if (to === "In review") return from === "Draft";
  if (to === "Signed") return from === "In review";
  return false;
}

export function WorkspaceApp() {
  const [activeView, setActiveView] = useState<View>("workspace");
  const [experiments, setExperiments] = useState(initialExperiments);
  const [selectedExperimentId, setSelectedExperimentId] = useState(initialExperiments[0].id);
  const [inventory, setInventory] = useState(initialInventory);
  const [connectors, setConnectors] = useState(initialConnectors);
  const [workflowStep, setWorkflowStep] = useState(2);
  const [sequence, setSequence] = useState(defaultSequence);
  const [search, setSearch] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftProject, setDraftProject] = useState("Cloning");
  const [draftBlock, setDraftBlock] = useState("Objective\nDesign and document the next wet-lab step.");
  const [copilotNote, setCopilotNote] = useState("Ready to summarize an experiment or suggest next steps.");
  const [activity, setActivity] = useState<ActivityEvent[]>([
    { id: "seed-1", message: "Workspace opened" },
    { id: "seed-2", message: "BioPython Local connector available" },
    { id: "seed-3", message: "EXP-1038 moved to review" }
  ]);
  const activityCounter = useRef(0);

  const selectedExperiment = experiments.find((experiment) => experiment.id === selectedExperimentId) ?? experiments[0];
  const cleanSequence = cleanDna(sequence);
  const sequenceStats = useMemo(
    () => ({
      length: cleanSequence.length,
      gc: gcPercent(cleanSequence),
      orfs: findOrfs(cleanSequence)
    }),
    [cleanSequence]
  );

  const filteredExperiments = experiments.filter((experiment) =>
    [experiment.title, experiment.project, experiment.owner, experiment.status].join(" ").toLowerCase().includes(search.toLowerCase())
  );

  function log(message: string) {
    activityCounter.current += 1;
    const id = `activity-${activityCounter.current}`;
    setActivity((items) => [{ id, message: `${todayStamp()} - ${message}` }, ...items].slice(0, 8));
  }

  function createExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draftTitle.trim()) return;

    const experiment: Experiment = {
      id: nextExperimentId(experiments),
      title: draftTitle.trim(),
      project: draftProject,
      owner: "You",
      status: "Draft",
      updated: "Just now",
      blocks: draftBlock
        .split("\n")
        .map((block) => block.trim())
        .filter(Boolean)
    };

    if (!experiment.blocks.length) {
      experiment.blocks = ["Untitled note"];
    }

    setExperiments((items) => [experiment, ...items]);
    setSelectedExperimentId(experiment.id);
    setActiveView("experiments");
    setDraftTitle("");
    log(`Created ${experiment.id}`);
  }

  function updateExperimentStatus(status: Experiment["status"]) {
    if (!canTransitionExperiment(selectedExperiment.status, status)) {
      log(`Blocked ${selectedExperiment.id} transition from ${selectedExperiment.status} to ${status}`);
      return;
    }

    setExperiments((items) =>
      items.map((experiment) =>
        experiment.id === selectedExperiment.id ? { ...experiment, status, updated: "Just now" } : experiment
      )
    );
    log(`${selectedExperiment.id} marked ${status}`);
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
    setConnectors((items) => items.map((item) => (item.id === id ? { ...item, enabled: !item.enabled } : item)));
    log(`${connector?.enabled ? "Disabled" : "Enabled"} connector ${id}`);
  }

  function runConnector(id: string) {
    const connector = connectors.find((item) => item.id === id);
    if (!connector?.enabled) {
      log(`Blocked disabled connector ${id}`);
      return;
    }
    setConnectors((items) => items.map((item) => (item.id === id ? { ...item, lastRun: "Completed just now" } : item)));
    log(`Ran connector job ${id}`);
  }

  function generateCopilotNote() {
    const note = `${selectedExperiment.id}: ${selectedExperiment.title}. Suggested next action: verify ${sequenceStats.length} bp sequence context, confirm reagent lots, then move record to review when observations are entered.`;
    setCopilotNote(note);
    log("Generated copilot note");
  }

  return (
    <main className="min-h-screen bg-[#f7f8f5]">
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
              {activity.slice(0, 5).map((item) => (
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
            </div>
            <button
              onClick={() => setActiveView("experiments")}
              className="inline-flex items-center gap-2 rounded-md bg-fern px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#1d513c]"
            >
              <Plus size={16} />
              New experiment
            </button>
          </header>

          {activeView === "workspace" && (
            <div className="mt-6 grid gap-4">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Metric icon={FlaskConical} label="Open experiments" value={String(experiments.length)} />
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
                <ExperimentPanel
                  experiment={selectedExperiment}
                  onReview={() => updateExperimentStatus("In review")}
                  onSign={() => updateExperimentStatus("Signed")}
                />
                <CopilotPanel note={copilotNote} onGenerate={generateCopilotNote} />
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
                    disabled={!draftTitle.trim()}
                    className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-4 py-2 text-sm font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:bg-black/20"
                  >
                    <Save size={16} />
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
                  {filteredExperiments.map((experiment) => (
                    <button
                      key={experiment.id}
                      onClick={() => setSelectedExperimentId(experiment.id)}
                      className={`rounded-md border p-3 text-left transition ${
                        experiment.id === selectedExperiment.id ? "border-fern bg-[#edf5ef]" : "border-black/10 hover:bg-black/5"
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
                  ))}
                </div>
              </section>
            </div>
          )}

          {activeView === "sequences" && (
            <section className="mt-6 rounded-md border border-black/10 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-semibold text-ink">Sequence analyzer</h2>
                <button
                  onClick={() => {
                    setSequence(defaultSequence);
                    log("Loaded demo plasmid sequence");
                  }}
                  className="rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5"
                >
                  Load demo sequence
                </button>
              </div>
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
              <div className="mt-4 grid gap-3">
                {connectors.map((connector) => (
                  <div key={connector.id} className="grid gap-3 rounded-md border border-black/10 p-4 md:grid-cols-[1fr_auto] md:items-center">
                    <div>
                      <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                        {connector.enabled ? <CheckCircle2 size={16} className="text-fern" /> : <Network size={16} className="text-graphite" />}
                        {connector.name}
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
                        disabled={!connector.enabled}
                        className="inline-flex items-center gap-2 rounded-md bg-fern px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:bg-black/20"
                      >
                        <Play size={14} />
                        Run
                      </button>
                    </div>
                  </div>
                ))}
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
  experiment: Experiment;
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

function CopilotPanel({ note, onGenerate }: { note: string; onGenerate: () => void }) {
  return (
    <section className="rounded-md border border-black/10 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <BrainCircuit size={17} />
          Lab copilot
        </div>
        <button onClick={onGenerate} className="inline-flex items-center gap-2 rounded-md border border-black/10 px-3 py-2 text-xs font-medium hover:bg-black/5">
          <Wand2 size={14} />
          Generate
        </button>
      </div>
      <p className="mt-4 rounded-md bg-[#fbfbf8] p-3 text-sm leading-6 text-graphite">{note}</p>
      <div className="mt-4 flex items-center gap-2 text-xs text-graphite">
        <History size={14} />
        Suggestions are stored in the local session audit trail.
      </div>
    </section>
  );
}
