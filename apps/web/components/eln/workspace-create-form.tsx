"use client";

import { FormEvent, useState } from "react";
import type { WorkspaceCategory } from "@helixos/types";

import { CATEGORY_TAXONOMY, OTHER_SUBCATEGORY } from "../../lib/workspace-taxonomy";

export type WorkspaceCreateValues = {
  name: string;
  category: WorkspaceCategory;
  subcategory: string | null;
};

export function WorkspaceCreateForm({
  pending = false,
  onSubmit,
  onCancel,
  compact = false
}: {
  pending?: boolean;
  onSubmit: (values: WorkspaceCreateValues) => void;
  onCancel?: () => void;
  compact?: boolean;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<WorkspaceCategory>("molecular_biology");
  const [subcategory, setSubcategory] = useState("");
  const [subcategoryOther, setSubcategoryOther] = useState("");

  const activeCategory = CATEGORY_TAXONOMY.find((entry) => entry.value === category);
  const categoryHasSubcategories = (activeCategory?.subcategories.length ?? 0) > 0;

  function resolvedSubcategory(): string | null {
    if (!categoryHasSubcategories) return null;
    if (subcategory === OTHER_SUBCATEGORY) {
      return subcategoryOther.trim() || null;
    }
    return subcategory || null;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    onSubmit({
      name: name.trim(),
      category,
      subcategory: resolvedSubcategory()
    });
  }

  const fieldClass =
    "rounded-md border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-fern";

  return (
    <form
      onSubmit={handleSubmit}
      className={
        compact
          ? "mt-1 grid gap-2 rounded-md border border-black/10 bg-[#fbfbf8] p-2"
          : "grid gap-3 rounded-md border border-black/10 bg-[#fbfbf8] p-3"
      }
    >
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Workspace name"
        className={fieldClass}
        autoFocus
      />
      <label className="text-[11px] font-medium uppercase tracking-wide text-graphite">Category</label>
      <select
        value={category}
        onChange={(event) => {
          setCategory(event.target.value as WorkspaceCategory);
          setSubcategory("");
          setSubcategoryOther("");
        }}
        className={fieldClass}
      >
        {CATEGORY_TAXONOMY.map((entry) => (
          <option key={entry.value} value={entry.value}>
            {entry.label}
          </option>
        ))}
      </select>
      {categoryHasSubcategories ? (
        <>
          <label className="text-[11px] font-medium uppercase tracking-wide text-graphite">Subcategory</label>
          <select
            value={subcategory}
            onChange={(event) => setSubcategory(event.target.value)}
            className={fieldClass}
          >
            <option value="">Select subcategory…</option>
            {activeCategory?.subcategories.map((sub) => (
              <option key={sub} value={sub}>
                {sub}
              </option>
            ))}
            <option value={OTHER_SUBCATEGORY}>Other…</option>
          </select>
          {subcategory === OTHER_SUBCATEGORY ? (
            <input
              value={subcategoryOther}
              onChange={(event) => setSubcategoryOther(event.target.value)}
              placeholder="Custom subcategory"
              className={fieldClass}
            />
          ) : null}
        </>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={pending || !name.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-fern px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1d513c] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "Creating…" : "Create workspace"}
        </button>
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-black/5"
          >
            Cancel
          </button>
        ) : null}
      </div>
    </form>
  );
}
