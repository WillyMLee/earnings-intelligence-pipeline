import { useMemo, useState } from "react";
import type { CompanyListing } from "../lib/convex";
import { CompanyLogo } from "./CompanyLogo";

type GroupMode = "alphabetical" | "sector";

export function Sidebar({
  companies,
  activeTicker,
  onSelect,
}: {
  companies: CompanyListing[];
  activeTicker: string | null;
  onSelect: (ticker: string) => void;
}) {
  const [groupMode, setGroupMode] = useState<GroupMode>("alphabetical");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return companies;
    return companies.filter(
      (c) => c.company.toLowerCase().includes(q) || c.ticker.toLowerCase().includes(q)
    );
  }, [companies, query]);

  const groups = useMemo(() => {
    if (groupMode === "alphabetical") {
      const byLetter = new Map<string, CompanyListing[]>();
      for (const c of filtered) {
        const letter = c.company[0]?.toUpperCase() ?? "#";
        const key = /[A-Z]/.test(letter) ? letter : "#";
        const list = byLetter.get(key) ?? [];
        list.push(c);
        byLetter.set(key, list);
      }
      return Array.from(byLetter.entries()).sort(([a], [b]) => a.localeCompare(b));
    }
    const bySector = new Map<string, CompanyListing[]>();
    for (const c of filtered) {
      const key = c.sector ?? "Unclassified";
      const list = bySector.get(key) ?? [];
      list.push(c);
      bySector.set(key, list);
    }
    return Array.from(bySector.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered, groupMode]);

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-black/[0.06] bg-white dark:border-white/[0.08] dark:bg-[#0e0f13]">
      <div className="border-b border-black/[0.06] p-4 dark:border-white/[0.08]">
        <input
          type="search"
          placeholder="Search companies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-lg border border-black/[0.08] bg-black/[0.02] px-3 py-1.5 text-[13px] text-[#15171c] outline-none placeholder:text-[#9a9ea8] focus:border-accent dark:border-white/[0.1] dark:bg-white/[0.03] dark:text-[#e7e8ea]"
        />
        <div className="mt-3 flex gap-1 rounded-lg bg-black/[0.03] p-0.5 dark:bg-white/[0.04]">
          {(["alphabetical", "sector"] as GroupMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setGroupMode(mode)}
              className={`flex-1 rounded-md py-1 text-[11px] font-semibold capitalize transition-colors ${
                groupMode === mode
                  ? "bg-white text-[#15171c] shadow-sm dark:bg-[#1c1d22] dark:text-[#e7e8ea]"
                  : "text-[#8b8f99]"
              }`}
            >
              {mode === "alphabetical" ? "A–Z" : "Sector"}
            </button>
          ))}
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {groups.length === 0 && (
          <div className="px-3 py-6 text-center text-[12px] text-[#9a9ea8]">No matches.</div>
        )}
        {groups.map(([label, items]) => (
          <div key={label} className="mb-3">
            <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#9a9ea8]">
              {label}
            </div>
            {items
              .slice()
              .sort((a, b) => a.company.localeCompare(b.company))
              .map((c) => (
                <button
                  key={c.ticker}
                  onClick={() => onSelect(c.ticker)}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors ${
                    activeTicker === c.ticker
                      ? "bg-accent-soft dark:bg-accent/15"
                      : "hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
                  }`}
                >
                  <CompanyLogo ticker={c.ticker} company={c.company} size={22} />
                  <span className="truncate text-[13px] font-medium text-[#2b2e35] dark:text-[#dcdee2]">
                    {c.company}
                  </span>
                </button>
              ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
