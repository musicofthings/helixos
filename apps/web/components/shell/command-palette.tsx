"use client";

import { LoaderCircle, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export type CommandPaletteItem = {
  id: string;
  label: string;
  group: string;
  keywords?: string[];
  disabled?: boolean;
  run: () => void | Promise<void>;
};

type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: CommandPaletteItem[];
};

export function CommandPalette({ open, onOpenChange, items }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [runningId, setRunningId] = useState<string | null>(null);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return items;
    }

    return items.filter((item) => {
      const haystack = [item.label, item.group, ...(item.keywords ?? [])].join(" ").toLowerCase();
      return haystack.includes(normalized);
    });
  }, [items, query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(0);
      setRunningId(null);
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onOpenChange(false);
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((index) => Math.min(filteredItems.length - 1, index + 1));
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((index) => Math.max(0, index - 1));
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, filteredItems.length, onOpenChange]);

  async function execute(item: CommandPaletteItem) {
    if (item.disabled || runningId) {
      return;
    }

    setRunningId(item.id);
    try {
      await item.run();
      onOpenChange(false);
    } finally {
      setRunningId(null);
    }
  }

  if (!open) {
    return null;
  }

  const grouped = filteredItems.reduce<Record<string, CommandPaletteItem[]>>((groups, item) => {
    groups[item.group] = groups[item.group] ?? [];
    groups[item.group].push(item);
    return groups;
  }, {});

  let itemIndex = -1;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 px-4 py-16">
      <div className="w-full max-w-xl overflow-hidden rounded-lg border border-black/10 bg-white shadow-2xl">
        <div className="flex items-center gap-2 border-b border-black/10 px-4 py-3">
          <Search size={16} className="text-graphite" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                const item = filteredItems[activeIndex];
                if (item) {
                  void execute(item);
                }
              }
            }}
            placeholder="Search commands..."
            className="w-full bg-transparent text-sm text-ink outline-none"
          />
          <kbd className="rounded border border-black/10 px-2 py-0.5 text-[10px] text-graphite">Esc</kbd>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {filteredItems.length ? (
            Object.entries(grouped).map(([group, groupItems]) => (
              <div key={group} className="px-2 py-1">
                <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-graphite">{group}</div>
                {groupItems.map((item) => {
                  itemIndex += 1;
                  const currentIndex = itemIndex;
                  const isActive = currentIndex === activeIndex;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      disabled={item.disabled}
                      onMouseEnter={() => setActiveIndex(currentIndex)}
                      onClick={() => void execute(item)}
                      className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${
                        isActive ? "bg-[#edf5ef] text-ink" : "text-graphite hover:bg-black/5"
                      } disabled:cursor-not-allowed disabled:opacity-50`}
                    >
                      <span>{item.label}</span>
                      {runningId === item.id ? <LoaderCircle size={14} className="animate-spin" /> : null}
                    </button>
                  );
                })}
              </div>
            ))
          ) : (
            <div className="px-4 py-6 text-sm text-graphite">No matching commands.</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function useCommandPaletteShortcut(onOpen: () => void) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isMetaK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (!isMetaK) {
        return;
      }
      event.preventDefault();
      onOpen();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpen]);
}
