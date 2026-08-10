import { useEffect, useMemo, useState } from "react";
import { listCalendarEvents, listRecentEarnings, type CalendarEvent, type PostEarningsSummary } from "../lib/convex";
import { IndexBar } from "../components/IndexBar";
import { CompanyLogo } from "../components/CompanyLogo";
import { ReactionBadge } from "../components/Badge";
import { stripCitations } from "../lib/citations";
import { relativeDay, beatMiss } from "../lib/format";
import { COVERAGE_GROUPS } from "../lib/coverageGroups";
import { bestHighlight, sortByReportTiming } from "../lib/reporting";
import { CoverageGroupIcon } from "../components/CoverageGroupIcon";
import { TickerStatusChip } from "../components/TickerStatusChip";
import { briefCaptured, eventStatus, FULL_2026_CALENDAR_WINDOW, Q2_2026_WINDOW, seasonEventByTicker } from "../lib/earningsStatus";

export function Dashboard({ onOpenCompany, onOpenOverview }: { onOpenCompany: (ticker: string) => void; onOpenOverview: (groupId: string) => void }) {
  const [summaries, setSummaries] = useState<PostEarningsSummary[] | null>(null);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);

  useEffect(() => {
    Promise.all([
      listRecentEarnings(250),
      listCalendarEvents(FULL_2026_CALENDAR_WINDOW.start, FULL_2026_CALENDAR_WINDOW.end),
    ])
      .then(([summaryRows, calendarRows]) => {
        setSummaries(summaryRows);
        setEvents(calendarRows);
      })
      .catch(() => {
        setSummaries([]);
        setEvents([]);
      });
  }, []);

  const view = useMemo(() => {
    if (!summaries || !events) return null;
    const recent = sortByReportTiming(summaries).slice(0, 8);
    const q2ByTicker = seasonEventByTicker(events, summaries, Q2_2026_WINDOW.start, Q2_2026_WINDOW.end);
    const reported = Array.from(q2ByTicker.values()).filter((event) => eventStatus(event) === "reported");
    const upcoming = Array.from(q2ByTicker.values()).filter((event) => eventStatus(event) === "upcoming");
    const captured = reported.filter((event) => briefCaptured(event, summaries)).length;
    const withConsensus = recent.filter((row) => row.revenueActualUsd !== null && row.revenueConsensusUsd !== null);
    const beats = withConsensus.filter((row) => beatMiss(row.revenueActualUsd, row.revenueConsensusUsd) === "beat").length;
    const reactions = recent.flatMap((row) => row.reactionPct == null ? [] : [row.reactionPct]);
    return {
      recent,
      q2ByTicker,
      universe: q2ByTicker.size,
      reported: reported.length,
      upcoming: upcoming.length,
      captured,
      beatRate: withConsensus.length ? Math.round((beats / withConsensus.length) * 100) : null,
      avgReaction: reactions.length ? reactions.reduce((sum, value) => sum + value, 0) / reactions.length : null,
    };
  }, [summaries, events]);

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-6 sm:px-8 sm:py-14">
      <header className="mb-6">
        <h1 className="text-[28px] font-extrabold tracking-tight text-[#15171c] dark:text-[#e7e8ea] sm:text-[40px]">Dashboard</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">
          Current-season reporting progress and the latest intelligence across the full coverage universe.
        </p>
      </header>

      <IndexBar />

      {view && (
        <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <StatTile label="Coverage universe" value={String(view.universe)} note="Unique calendar companies" />
          <StatTile label="Q2 reported" value={String(view.reported)} tone="up" note="Report date has passed" />
          <StatTile label="Q2 upcoming" value={String(view.upcoming)} tone="pending" note="Still left to report" />
          <StatTile label="Briefs ready" value={String(view.captured)} note={`${view.reported ? Math.round((view.captured / view.reported) * 100) : 0}% of reported`} />
          <StatTile label="Revenue beat rate" value={view.beatRate == null ? "—" : `${view.beatRate}%`} />
          <StatTile label="Avg. reaction" value={view.avgReaction == null ? "—" : `${view.avgReaction >= 0 ? "+" : ""}${view.avgReaction.toFixed(1)}%`} tone={view.avgReaction == null ? undefined : view.avgReaction >= 0 ? "up" : "down"} />
        </div>
      )}

      <section className="mb-9">
        <div className="mb-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Coverage overviews</div>
          <div className="mt-1 text-[13px] text-[#9a9ea8]">Green has reported, amber is upcoming, and gray is awaiting a confirmed date.</div>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {COVERAGE_GROUPS.map((group) => {
            const groupEvents = Array.from(group.tickers).map((ticker) => view?.q2ByTicker.get(ticker));
            const reported = groupEvents.filter((event) => eventStatus(event) === "reported").length;
            const upcoming = groupEvents.filter((event) => eventStatus(event) === "upcoming").length;
            const scheduled = reported + upcoming;
            const pending = group.tickers.size - scheduled;
            const percentage = group.tickers.size ? Math.round((reported / group.tickers.size) * 100) : 0;
            return (
              <button key={group.id} onClick={() => onOpenOverview(group.id)} className="rounded-card border border-black/[0.06] bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:border-accent/35 hover:shadow-sm dark:border-white/[0.08] dark:bg-[#121317]">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-2.5 text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]"><CoverageGroupIcon icon={group.icon} size={30} /><span className="truncate">{group.name}</span></span>
                  <span className="text-[11px] font-semibold text-accent">{percentage}%</span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[12px] leading-relaxed text-[#7a7f89] dark:text-[#8f949f]">{group.description}</p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {Array.from(group.tickers).map((ticker) => <TickerStatusChip key={ticker} ticker={ticker} event={view?.q2ByTicker.get(ticker)} compact />)}
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-black/[0.05] dark:bg-white/[0.06]"><div className="h-full rounded-full bg-accent" style={{ width: `${percentage}%` }} /></div>
                <div className="mt-1.5 text-[10px] text-[#9a9ea8]">{reported} reported · {upcoming} upcoming · {pending} date pending</div>
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-end justify-between gap-4">
          <div><div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Recent highlights</div><div className="mt-1 text-[12px] text-[#9a9ea8]">Ordered by report date and market session.</div></div>
          {view && <div className="text-[11px] text-[#9a9ea8]">{view.recent.length} latest</div>}
        </div>
        <div className="grid min-w-0 gap-3 xl:grid-cols-2">
          {!view && <div className="text-[13px] text-[#9a9ea8]">Loading…</div>}
          {view?.recent.length === 0 && <div className="text-[13px] text-[#9a9ea8]">No completed reports captured yet.</div>}
          {view?.recent.map((row) => {
            const highlightText = stripCitations(bestHighlight(row)).text;
            return (
              <button key={row._id} onClick={() => onOpenCompany(row.ticker)} className="flex w-full min-w-0 items-start gap-3 overflow-hidden rounded-card border border-black/[0.06] bg-white p-3.5 text-left transition-colors hover:border-accent/40 dark:border-white/[0.08] dark:bg-[#121317] sm:items-center">
                <span className="shrink-0"><CompanyLogo ticker={row.ticker} company={row.company} size={36} /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-baseline gap-2">
                        <span className="truncate text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{row.company}</span>
                        <span className="shrink-0 font-mono text-[10px] text-[#9a9ea8] sm:text-[11px]">{row.ticker}</span>
                      </div>
                      <div className="mt-0.5 text-[10px] leading-snug text-[#9a9ea8] sm:text-[11px]">{relativeDay(row.reportDate)} · {row.reportTime}</div>
                    </div>
                    <span className="shrink-0"><ReactionBadge pct={row.reactionPct} /></span>
                  </div>
                  {highlightText && <div className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">{highlightText}</div>}
                </div>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function StatTile({ label, value, tone, note }: { label: string; value: string; tone?: "up" | "down" | "pending"; note?: string }) {
  return <div className="rounded-card border border-black/[0.06] bg-white p-3.5 dark:border-white/[0.08] dark:bg-[#121317]"><div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{label}</div><div className={`mt-1 text-[21px] font-bold tabular-nums ${tone === "up" ? "text-emerald-600 dark:text-emerald-400" : tone === "down" ? "text-rose-600 dark:text-rose-400" : tone === "pending" ? "text-amber-600 dark:text-amber-400" : "text-[#15171c] dark:text-[#e7e8ea]"}`}>{value}</div>{note && <div className="mt-0.5 text-[10px] text-[#9a9ea8]">{note}</div>}</div>;
}
