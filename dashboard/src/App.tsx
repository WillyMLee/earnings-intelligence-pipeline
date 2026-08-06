import { useEffect, useMemo, useState } from "react";
import { listRecentEarnings, listSectors, type PostEarningsSummary } from "./lib/convex";
import { EarningsCard } from "./components/EarningsCard";

type LoadState = "loading" | "ready" | "error";

export default function App() {
  const [summaries, setSummaries] = useState<PostEarningsSummary[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [activeSector, setActiveSector] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    Promise.all([listRecentEarnings(60, activeSector ?? undefined), listSectors()])
      .then(([recent, allSectors]) => {
        if (cancelled) return;
        setSummaries(recent);
        setSectors(allSectors);
        setState("ready");
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [activeSector]);

  const groupedByDate = useMemo(() => {
    const groups = new Map<string, PostEarningsSummary[]>();
    for (const summary of summaries) {
      const list = groups.get(summary.reportDate) ?? [];
      list.push(summary);
      groups.set(summary.reportDate, list);
    }
    return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [summaries]);

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:py-14">
      <header className="mb-10">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 dark:border-white/[0.08] dark:bg-[#121317]">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
          </span>
          <span className="text-[12px] font-medium text-[#5b5f6b] dark:text-[#9a9ea8]">Live earnings feed</span>
        </div>
        <h1 className="text-[32px] font-extrabold tracking-tight text-[#15171c] dark:text-[#e7e8ea] sm:text-[40px]">
          Earnings Intelligence
        </h1>
        <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">
          A running record of public-company earnings results, sourced by an automated research
          pipeline and checked against Street consensus as each report lands.
        </p>
      </header>

      {sectors.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-2">
          <FilterPill label="All sectors" active={activeSector === null} onClick={() => setActiveSector(null)} />
          {sectors.map((sector) => (
            <FilterPill
              key={sector}
              label={sector}
              active={activeSector === sector}
              onClick={() => setActiveSector(sector)}
            />
          ))}
        </div>
      )}

      {state === "loading" && <EmptyState message="Loading recent earnings…" />}
      {state === "error" && (
        <EmptyState message={`Couldn't load earnings data: ${error}`} tone="error" />
      )}
      {state === "ready" && groupedByDate.length === 0 && (
        <EmptyState message="No earnings recorded for this sector yet." />
      )}

      {state === "ready" && (
        <div className="flex flex-col gap-10">
          {groupedByDate.map(([date, items]) => (
            <section key={date}>
              <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-[#8b8f99] dark:text-[#7d818c]">
                {new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })}
              </h2>
              <div className="flex flex-col gap-3">
                {items.map((summary) => (
                  <EarningsCard key={summary._id} summary={summary} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <footer className="mt-16 border-t border-black/[0.06] pt-6 text-[12px] text-[#9a9ea8] dark:border-white/[0.08]">
        Figures are Street consensus/guidance unless noted as reported. Not investment advice.
      </footer>
    </div>
  );
}

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors ${
        active
          ? "border-accent bg-accent-soft text-accent dark:bg-accent/20"
          : "border-black/[0.08] bg-white text-[#5b5f6b] hover:border-black/20 dark:border-white/[0.1] dark:bg-[#121317] dark:text-[#9a9ea8]"
      }`}
    >
      {label}
    </button>
  );
}

function EmptyState({ message, tone = "default" }: { message: string; tone?: "default" | "error" }) {
  return (
    <div
      className={`rounded-card border border-dashed px-6 py-16 text-center text-[14px] ${
        tone === "error"
          ? "border-rose-200 text-rose-600 dark:border-rose-900 dark:text-rose-400"
          : "border-black/10 text-[#9a9ea8] dark:border-white/10"
      }`}
    >
      {message}
    </div>
  );
}
