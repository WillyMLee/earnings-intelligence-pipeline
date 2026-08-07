import { useEffect, useMemo, useState } from "react";
import { getReportingProgress, listCompanies, listRecentEarnings, type CompanyListing, type PostEarningsSummary, type ReportingProgress } from "../lib/convex";
import { COVERAGE_GROUPS, getCoverageGroup } from "../lib/coverageGroups";
import { cycleCutoff, currentWeekWindow, sortByReportTiming } from "../lib/reporting";
import { beatMiss, fmtPct, fmtUsdCompact, relativeDay } from "../lib/format";
import { CompanyLogo } from "../components/CompanyLogo";
import { ReactionBadge } from "../components/Badge";
import { CoverageGroupIcon } from "../components/CoverageGroupIcon";

export function SectorOverviews({
  groupId,
  onSelectGroup,
  onOpenCompany,
}: {
  groupId: string;
  onSelectGroup: (id: string) => void;
  onOpenCompany: (ticker: string) => void;
}) {
  const [companies, setCompanies] = useState<CompanyListing[]>([]);
  const [summaries, setSummaries] = useState<PostEarningsSummary[] | null>(null);
  const [progress, setProgress] = useState<ReportingProgress | null>(null);
  const group = getCoverageGroup(groupId);

  useEffect(() => {
    Promise.all([listCompanies(), listRecentEarnings(200)])
      .then(([companyRows, summaryRows]) => {
        setCompanies(companyRows);
        setSummaries(sortByReportTiming(summaryRows));
      })
      .catch(() => setSummaries([]));
  }, []);

  useEffect(() => {
    const week = currentWeekWindow();
    getReportingProgress(week.start, week.end, Array.from(group.tickers)).then(setProgress).catch(() => setProgress(null));
  }, [group.id]);

  const view = useMemo(() => {
    const tracked = companies.filter((company) => group.tickers.has(company.ticker));
    const groupRows = (summaries ?? []).filter((row) => group.tickers.has(row.ticker));
    const latest = new Map<string, PostEarningsSummary>();
    for (const row of groupRows) if (!latest.has(row.ticker)) latest.set(row.ticker, row);
    const current = Array.from(latest.values()).filter((row) => row.reportDate >= cycleCutoff());
    const withConsensus = current.filter((row) => row.revenueActualUsd != null && row.revenueConsensusUsd != null);
    const beats = withConsensus.filter((row) => beatMiss(row.revenueActualUsd, row.revenueConsensusUsd) === "beat").length;
    const reactions = current.flatMap((row) => (row.reactionPct == null ? [] : [row.reactionPct]));
    return {
      tracked,
      current,
      reportingPct: group.tickers.size ? Math.round((current.length / group.tickers.size) * 100) : 0,
      beatRate: withConsensus.length ? Math.round((beats / withConsensus.length) * 100) : null,
      avgReaction: reactions.length ? reactions.reduce((sum, value) => sum + value, 0) / reactions.length : null,
    };
  }, [companies, summaries, group]);

  return (
    <div className="mx-auto max-w-6xl px-5 py-10 sm:py-14">
      <header className="mb-7">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Coverage overviews</div>
        <div className="mt-2 flex items-center gap-3"><CoverageGroupIcon icon={group.icon} size={44} /><h1 className="text-[32px] font-extrabold tracking-tight text-[#15171c] dark:text-[#e7e8ea] sm:text-[40px]">{group.name}</h1></div>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">{group.description}</p>
        <p className="mt-2 font-mono text-[11px] text-[#9a9ea8]">Includes {Array.from(group.tickers).join(" · ")}</p>
      </header>

      <div className="mb-7 flex gap-2 overflow-x-auto pb-1">
        {COVERAGE_GROUPS.map((item) => (
          <button
            key={item.id}
            onClick={() => onSelectGroup(item.id)}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-[12px] font-semibold transition-colors ${
              item.id === group.id
                ? "border-accent bg-accent-soft text-accent dark:bg-accent/20"
                : "border-black/[0.08] bg-white text-[#5b5f6b] dark:border-white/[0.1] dark:bg-[#121317] dark:text-[#9a9ea8]"
            }`}
          >
            {item.shortName}
          </button>
        ))}
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <OverviewStat label="Constituents" value={String(group.tickers.size)} note={`${view.tracked.length} with archived reports`} />
        <OverviewStat
          label="Reported this week"
          value={progress ? (progress.total ? `${progress.percent}%` : "—") : `${view.reportingPct}%`}
          note={progress ? (progress.total ? `${progress.reported} of ${progress.total} scheduled` : "No reports scheduled") : `${view.current.length} of ${view.tracked.length} this cycle`}
        />
        <OverviewStat label="Revenue beat rate" value={view.beatRate == null ? "—" : `${view.beatRate}%`} />
        <OverviewStat
          label="Avg. reaction"
          value={view.avgReaction == null ? "—" : `${view.avgReaction >= 0 ? "+" : ""}${view.avgReaction.toFixed(1)}%`}
          tone={view.avgReaction == null ? undefined : view.avgReaction >= 0 ? "up" : "down"}
        />
      </div>

      <section>
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Latest reports</div>
            <div className="mt-1 text-[13px] text-[#9a9ea8]">Most recent report for each company in this group.</div>
          </div>
        </div>
        <div className="overflow-hidden rounded-card border border-black/[0.06] bg-white dark:border-white/[0.08] dark:bg-[#121317]">
          {view.current.length === 0 && <div className="px-5 py-12 text-center text-[13px] text-[#9a9ea8]">No reports in the current 45-day cycle yet.</div>}
          {view.current.map((row, index) => {
            const verdict = beatMiss(row.revenueActualUsd, row.revenueConsensusUsd);
            return (
              <button
                key={row._id}
                onClick={() => onOpenCompany(row.ticker)}
                className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.03] ${index ? "border-t border-black/[0.05] dark:border-white/[0.06]" : ""}`}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <CompanyLogo ticker={row.ticker} company={row.company} size={34} />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{row.company}</span>
                      <span className="font-mono text-[11px] text-[#9a9ea8]">{row.ticker}</span>
                    </div>
                    <div className="mt-0.5 text-[11px] text-[#9a9ea8]">
                      {relativeDay(row.reportDate)} · {row.reportTime} · Revenue {fmtUsdCompact(row.revenueActualUsd)}
                      {row.revenueYoyPct != null ? ` · ${fmtPct(row.revenueYoyPct)} YoY` : ""}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {verdict && <span className={`text-[10px] font-bold uppercase ${verdict === "beat" ? "text-emerald-600 dark:text-emerald-400" : verdict === "miss" ? "text-rose-600 dark:text-rose-400" : "text-[#8b8f99]"}`}>{verdict}</span>}
                  <ReactionBadge pct={row.reactionPct} />
                </div>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function OverviewStat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "up" | "down" }) {
  return (
    <div className="rounded-card border border-black/[0.06] bg-white p-4 dark:border-white/[0.08] dark:bg-[#121317]">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{label}</div>
      <div className={`mt-1 text-[22px] font-bold tabular-nums ${tone === "up" ? "text-emerald-600 dark:text-emerald-400" : tone === "down" ? "text-rose-600 dark:text-rose-400" : "text-[#15171c] dark:text-[#e7e8ea]"}`}>{value}</div>
      {note && <div className="mt-0.5 text-[11px] text-[#9a9ea8]">{note}</div>}
    </div>
  );
}
