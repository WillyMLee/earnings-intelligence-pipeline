import { useMemo, useState } from "react";
import type { CompanyListing } from "../lib/convex";
import type { Route } from "../lib/router";
import { CompanyLogo } from "./CompanyLogo";
import { MAG7_TICKERS, TOP100_TICKERS, TICKER_FILTER_LABEL, type TickerFilter } from "../lib/tickerGroups";

type GroupMode = "alphabetical" | "sector";

export function Sidebar({
  companies,
  activeTicker,
  route,
  onSelect,
  onNav,
}: {
  companies: CompanyListing[];
  activeTicker: string | null;
  route: Route;
  onSelect: (ticker: string) => void;
  onNav: (name: "dashboard" | "feed" | "sectors") => void;
}) {
  const [groupMode, setGroupMode] = useState<GroupMode>("alphabetical");
  const [tickerFilter, setTickerFilter] = useState<TickerFilter>("all");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    let list = companies;
    if (tickerFilter === "mag7") list = list.filter((c) => MAG7_TICKERS.has(c.ticker));
    if (tickerFilter === "top100") list = list.filter((c) => TOP100_TICKERS.has(c.ticker));
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (c) => c.company.toLowerCase().includes(q) || c.ticker.toLowerCase().includes(q)
    );
  }, [companies, query, tickerFilter]);

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
      <nav className="flex flex-col gap-0.5 border-b border-black/[0.06] p-3 dark:border-white/[0.08]">
        <NavLink label="Dashboard" active={route.name === "dashboard"} onClick={() => onNav("dashboard")} />
        <NavLink label="Sector overviews" active={route.name === "sectors"} onClick={() => onNav("sectors")} />
        <NavLink label="Feed" active={route.name === "feed"} onClick={() => onNav("feed")} />
      </nav>
      <div className="border-b border-black/[0.06] p-4 dark:border-white/[0.08]">
        <input
          type="search"
          placeholder="Search companies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-lg border border-black/[0.08] bg-black/[0.02] px-3 py-1.5 text-[13px] text-[#15171c] outline-none placeholder:text-[#9a9ea8] focus:border-accent dark:border-white/[0.1] dark:bg-white/[0.03] dark:text-[#e7e8ea]"
        />
        <select
          value={tickerFilter}
          onChange={(e) => setTickerFilter(e.target.value as TickerFilter)}
          className="mt-2 w-full appearance-none rounded-lg border border-black/[0.08] bg-black/[0.02] bg-[url('data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2210%22%20height%3D%226%22%20viewBox%3D%220%200%2010%206%22%3E%3Cpath%20d%3D%22M1%201l4%204%204-4%22%20stroke%3D%22%238b8f99%22%20stroke-width%3D%221.5%22%20fill%3D%22none%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E')] bg-[length:10px_6px] bg-[right_10px_center] bg-no-repeat px-3 py-1.5 text-[12px] font-medium text-[#2b2e35] outline-none focus:border-accent dark:border-white/[0.1] dark:bg-white/[0.03] dark:text-[#dcdee2]"
        >
          {(Object.keys(TICKER_FILTER_LABEL) as TickerFilter[]).map((key) => (
            <option key={key} value={key}>
              {TICKER_FILTER_LABEL[key]}
            </option>
          ))}
        </select>
        <div className="mt-2 flex gap-1 rounded-lg bg-black/[0.03] p-0.5 dark:bg-white/[0.04]">
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

function NavLink({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-2.5 py-1.5 text-left text-[13px] font-semibold transition-colors ${
        active
          ? "bg-accent-soft text-accent dark:bg-accent/15"
          : "text-[#5b5f6b] hover:bg-black/[0.03] dark:text-[#9a9ea8] dark:hover:bg-white/[0.04]"
      }`}
    >
      {label}
    </button>
  );
}
