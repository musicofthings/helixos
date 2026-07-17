import type { WorkspaceCategory } from "@helixos/types";

export type CategoryDef = {
  value: WorkspaceCategory;
  label: string;
  subcategories: string[];
};

/** Mirrors CATEGORY_SUBCATEGORIES in services/api/helixos/eln/schemas.py. */
export const CATEGORY_TAXONOMY: CategoryDef[] = [
  { value: "molecular_biology", label: "Molecular Biology", subcategories: [] },
  { value: "biochemistry", label: "Biochemistry", subcategories: [] },
  { value: "microbiology", label: "Microbiology", subcategories: [] },
  {
    value: "next_gen_sequencing",
    label: "Next Generation Sequencing",
    subcategories: ["DNA", "RNA", "Protein"]
  },
  {
    value: "digital_pathology",
    label: "Digital Pathology & Imaging",
    subcategories: ["Cells", "Tissues"]
  },
  {
    value: "programmable_bio",
    label: "Programmable Bio",
    subcategories: ["Single-cell experiments", "PerturbGen", "Protein-protein interaction studies"]
  },
  { value: "custom", label: "Custom", subcategories: [] }
];

export const OTHER_SUBCATEGORY = "__other__";

const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  CATEGORY_TAXONOMY.map((entry) => [entry.value, entry.label])
);

export function categoryLabel(category: string): string {
  return (
    CATEGORY_LABELS[category] ??
    category
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}
