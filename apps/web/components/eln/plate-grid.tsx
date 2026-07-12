"use client";

import type { Sample, SampleType } from "@helixos/types";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const COLUMNS = Array.from({ length: 12 }, (_, index) => index + 1);

export const SAMPLE_TYPE_STYLES: Record<SampleType, { dot: string; chip: string; label: string }> = {
  dna: { dot: "bg-emerald-500", chip: "bg-emerald-50 text-emerald-700", label: "DNA" },
  rna: { dot: "bg-sky-500", chip: "bg-sky-50 text-sky-700", label: "RNA" },
  protein: { dot: "bg-violet-500", chip: "bg-violet-50 text-violet-700", label: "Protein" },
  cell: { dot: "bg-amber-500", chip: "bg-amber-50 text-amber-700", label: "Cell" },
  tissue: { dot: "bg-rose-500", chip: "bg-rose-50 text-rose-700", label: "Tissue" },
  reagent: { dot: "bg-slate-400", chip: "bg-slate-100 text-slate-600", label: "Reagent" },
  other: { dot: "bg-neutral-400", chip: "bg-neutral-100 text-neutral-600", label: "Other" }
};

export function PlateGrid({
  samples,
  selectedSampleId,
  onSelectSample,
  onSelectEmptyWell
}: {
  samples: Sample[];
  selectedSampleId?: string;
  onSelectSample: (sampleId: string) => void;
  onSelectEmptyWell: (well: string) => void;
}) {
  const byWell = new Map<string, Sample>();
  for (const sample of samples) {
    if (sample.well_position) {
      byWell.set(sample.well_position.toUpperCase(), sample);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1">
        <thead>
          <tr>
            <th className="w-6" />
            {COLUMNS.map((column) => (
              <th key={column} className="w-9 pb-1 text-center text-[10px] font-medium text-graphite">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row}>
              <th className="pr-1 text-right text-[10px] font-medium text-graphite">{row}</th>
              {COLUMNS.map((column) => {
                const well = `${row}${column}`;
                const sample = byWell.get(well);
                const isSelected = sample && sample.id === selectedSampleId;
                const style = sample ? SAMPLE_TYPE_STYLES[sample.sample_type] : null;

                return (
                  <td key={well}>
                    <button
                      type="button"
                      title={sample ? `${well} · ${sample.name} (${sample.sample_type})` : `${well} · empty`}
                      onClick={() => (sample ? onSelectSample(sample.id) : onSelectEmptyWell(well))}
                      className={`flex h-9 w-9 items-center justify-center rounded-full border text-[9px] font-medium transition ${
                        sample
                          ? `${style?.chip ?? ""} border-transparent ${isSelected ? "ring-2 ring-fern ring-offset-1" : ""}`
                          : "border-dashed border-black/15 bg-[#fbfbf8] text-black/25 hover:border-fern hover:text-fern"
                      }`}
                    >
                      {sample ? <span className={`h-2 w-2 rounded-full ${style?.dot ?? ""}`} /> : "+"}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex flex-wrap gap-2">
        {Object.entries(SAMPLE_TYPE_STYLES).map(([type, style]) => (
          <span key={type} className="inline-flex items-center gap-1 text-[10px] text-graphite">
            <span className={`h-2 w-2 rounded-full ${style.dot}`} />
            {style.label}
          </span>
        ))}
      </div>
    </div>
  );
}
