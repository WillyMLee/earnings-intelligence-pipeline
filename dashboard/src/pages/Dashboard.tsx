import { useEffect, useMemo, useState } from "react";
import { getReportingProgress, listRecentEarnings, listCompanies, type PostEarningsSummary, type CompanyListing, type ReportingProgress } from "../lib/convex";
import { IndexBar } from "../components/IndexBar";
import { CompanyLogo } from "../components/CompanyLogo";
import { ReactionBadge } from "../components/Badge";
import { stripCitations } from "../lib/citations";
import { relativeDay, beatMiss } from "../lib/format";
import { COVERAGE_GROUPS } from "../lib/coverageGroups";
import { bestHighlight, cycleCutoff, currentWeekWindow, sortByReportTiming } from "../lib/reporting";

export function Dashboard({ onOpenCompany, onOpenOverview }: { onOpenCompany: (ticker: string) => void; onOpenOverview: (groupId: string) => void }) {
  const [recent, setRecent] = useState<PostEarningsSummary[] | null>(null);
  const [companies, setCompanies] = useState<CompanyListing[]>([]);
  const [progress, setProgress] = useState<ReportingProgress | null>(null);

  useEffect(() => {
    listRecentEarnings(30).then((rows) => setRecent(sortByReportTiming(rows).slice(0, 8))).catch(() => setRecent([]));
    listCompanies().then(setCompanies).catch(() => {});
    const week = currentWeekWindow();
    getReportingProgress(week.start, week.end).then(setProgress).catch(() => {});
  }, []);

  const stats = useMemo(() => {
    if (!recent) return null;
    const withConsensus = recent.filter((r) => r.revenueActualUsd !== null && r.revenueConsensusUsd !== null);
    const beats = withConsensus.filter((r) => beatMiss(r.revenueActualUsd, r.revenueConsensusUsd) === "beat").length;
    const avgReaction =
      recent.filter((r) => r.reactionPct !== null).reduce((sum, r) => sum + (r.reactionPct ?? 0), 0) /
        (recent.filter((r) => r.reactionPct !== null).length || 1);
    return {
      companiesTracked: companies.length,
      reportsShown: recent.length,
      reportedThisCycle: companies.length
        ? Math.round((companies.filter((company) => company.reportDate >= cycleCutoff()).length / companies.length) * 100)
        : 0,
      beatRate: withConsensus.length > 0 ? Math.round((beats / withConsensus.length) * 100) : null,
      avgReaction,
    };
  }, [recent, companies]);

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:py-14">
      <header className="mb-6">
        <h1 className="text-[32px] font-extrabold tracking-tight text-[#15171c] dark:text-[#e7e8ea] sm:text-[40px]">
          Dashboard
        </h1>
        <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">
          Markets at a glance, plus the most recent earnings highlights from your coverage universe.
        </p>
      </header>

      <IndexBar />

      {stats && (
        <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Companies tracked" value={String(stats.companiesTracked)} />
          <StatTile
            label="Reported this week"
            value={`${progress?.total ? progress.percent : stats.reportedThisCycle}%`}
            note={progress?.total ? `${progress.reported} of ${progress.total} scheduled` : "Calendar sync pending"}
          />
          <StatTile label="Revenue beat rate" value={stats.beatRate !== null ? `${stats.beatRate}%` : "—"} />
          <StatTile
            label="Avg. reaction"
            value={Number.isFinite(stats.avgReaction) ? `${stats.avgReaction >= 0 ? "+" : ""}${stats.avgReaction.toFixed(1)}%` : "—"}
            tone={stats.avgReaction >= 0 ? "up" : "down"}
          />
        </div>
      )}

      <div className="mb-8">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Coverage overviews</div>
            <div className="mt-1 text-[13px] text-[#9a9ea8]">Follow earnings as a connected industry story.</div>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {COVERAGE_GROUPS.slice(0, 3).map((group) => {
            const tracked = companies.filter((company) => group.tickers.has(company.ticker));
            const reported = tracked.filter((company) => company.reportDate >= cycleCutoff()).length;
            return (
              <button
                key={group.id}
                onClick={() => onOpenOverview(group.id)}
                className="rounded-card border border-black/[0.06] bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:border-accent/35 hover:shadow-sm dark:border-white/[0.08] dark:bg-[#121317]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{group.name}</span>
                  <span className="text-[11px] font-semibold text-accent">{tracked.length ? Math.round((reported / tracked.length) * 100) : 0}%</span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[12px] leading-relaxed text-[#7a7f89] dark:text-[#8f949f]">{group.description}</p>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-black/[0.05] dark:bg-white/[0.06]">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${tracked.length ? (reported / tracked.length) * 100 : 0}%` }} />
                </div>
                <div className="mt-1.5 text-[10px] text-[#9a9ea8]">{reported} of {tracked.length} reported this cycle</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Recent highlights</div>
          <div className="mt-1 text-[12px] text-[#9a9ea8]">Ordered by report date and market session.</div>
        </div>
        {stats && <div className="text-[11px] text-[#9a9ea8]">{stats.reportsShown} latest</div>}
      </div>
      <div className="flex flex-col gap-3">
        {recent === null && <div className="text-[13px] text-[#9a9ea8]">Loading…</div>}
        {recent?.length === 0 && <div className="text-[13px] text-[#9a9ea8]">No reports archived yet.</div>}
        {recent?.map((r) => {
          const highlightText = stripCitations(bestHighlight(r)).text;
          return (
            <button
              key={r._id}
              onClick={() => onOpenCompany(r.ticker)}
              className="flex items-center gap-3 rounded-card border border-black/[0.06] bg-white p-3.5 text-left transition-colors hover:border-accent/40 dark:border-white/[0.08] dark:bg-[#121317]"
            >
              <CompanyLogo ticker={r.ticker} company={r.company} size={36} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{r.company}</span>
                  <span className="font-mono text-[11px] text-[#9a9ea8]">{r.ticker}</span>
                  <span className="text-[11px] text-[#9a9ea8]">{relativeDay(r.reportDate)} · {r.reportTime}</span>
                </div>
                {highlightText && (
                  <div className="mt-0.5 truncate text-[12px] text-[#5b5f6b] dark:text-[#9a9ea8]">{highlightText}</div>
                )}
              </div>
              <ReactionBadge pct={r.reactionPct} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StatTile({ label, value, tone, note }: { label: string; value: string; tone?: "up" | "down"; note?: string }) {
  return (
    <div className="rounded-card border border-black/[0.06] bg-white p-3.5 dark:border-white/[0.08] dark:bg-[#121317]">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{label}</div>
      <div
        className={`mt-1 text-[18px] font-bold ${
          tone === "up" ? "text-emerald-600 dark:text-emerald-400" : tone === "down" ? "text-rose-600 dark:text-rose-400" : "text-[#15171c] dark:text-[#e7e8ea]"
        }`}
      >
        {value}
      </div>
      {note && <div className="mt-0.5 text-[10px] text-[#9a9ea8]">{note}</div>}
    </div>
  );
}
