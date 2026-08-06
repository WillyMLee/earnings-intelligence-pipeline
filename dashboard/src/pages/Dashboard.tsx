import { useEffect, useMemo, useState } from "react";
import { listRecentEarnings, listCompanies, type PostEarningsSummary, type CompanyListing } from "../lib/convex";
import { IndexBar } from "../components/IndexBar";
import { CompanyLogo } from "../components/CompanyLogo";
import { ReactionBadge } from "../components/Badge";
import { stripCitations } from "../lib/citations";
import { relativeDay, beatMiss } from "../lib/format";

export function Dashboard({ onOpenCompany }: { onOpenCompany: (ticker: string) => void }) {
  const [recent, setRecent] = useState<PostEarningsSummary[] | null>(null);
  const [companies, setCompanies] = useState<CompanyListing[]>([]);

  useEffect(() => {
    listRecentEarnings(8).then(setRecent).catch(() => setRecent([]));
    listCompanies().then(setCompanies).catch(() => {});
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
          <StatTile label="Recent reports" value={String(stats.reportsShown)} />
          <StatTile label="Revenue beat rate" value={stats.beatRate !== null ? `${stats.beatRate}%` : "—"} />
          <StatTile
            label="Avg. reaction"
            value={Number.isFinite(stats.avgReaction) ? `${stats.avgReaction >= 0 ? "+" : ""}${stats.avgReaction.toFixed(1)}%` : "—"}
            tone={stats.avgReaction >= 0 ? "up" : "down"}
          />
        </div>
      )}

      <div className="mb-4 text-[13px] font-semibold uppercase tracking-wide text-[#8b8f99]">Recent highlights</div>
      <div className="flex flex-col gap-3">
        {recent === null && <div className="text-[13px] text-[#9a9ea8]">Loading…</div>}
        {recent?.length === 0 && <div className="text-[13px] text-[#9a9ea8]">No reports archived yet.</div>}
        {recent?.map((r) => {
          const topBullet = (r.financialHighlights ?? [])[0];
          const highlightText = topBullet ? stripCitations(topBullet.text).text : (r.keyMetrics ?? [])[0];
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
                  <span className="text-[11px] text-[#9a9ea8]">{relativeDay(r.reportDate)}</span>
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

function StatTile({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
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
    </div>
  );
}
