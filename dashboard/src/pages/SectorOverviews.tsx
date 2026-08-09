import { useEffect, useMemo, useState } from "react";
import { listCalendarEvents, listRecentEarnings, type CalendarEvent, type PostEarningsSummary } from "../lib/convex";
import { COVERAGE_GROUPS, getCoverageGroup } from "../lib/coverageGroups";
import { beatMiss, fmtPct, fmtUsdCompact, relativeDay } from "../lib/format";
import { CompanyLogo } from "../components/CompanyLogo";
import { ReactionBadge } from "../components/Badge";
import { CoverageGroupIcon } from "../components/CoverageGroupIcon";
import { TickerStatusChip } from "../components/TickerStatusChip";
import { briefCaptured, eventStatus, Q2_2026_WINDOW, seasonEventByTicker } from "../lib/earningsStatus";
import { displayCompanyName } from "../lib/companyNames";
import { sortByReportTiming } from "../lib/reporting";

export function SectorOverviews({ groupId, onSelectGroup, onOpenCompany }: { groupId: string; onSelectGroup: (id: string) => void; onOpenCompany: (ticker: string) => void }) {
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [summaries, setSummaries] = useState<PostEarningsSummary[] | null>(null);
  const group = getCoverageGroup(groupId);

  useEffect(() => {
    Promise.all([
      listCalendarEvents(Q2_2026_WINDOW.start, Q2_2026_WINDOW.end),
      listRecentEarnings(250),
    ])
      .then(([calendarRows, summaryRows]) => {
        setEvents(calendarRows);
        setSummaries(sortByReportTiming(summaryRows));
      })
      .catch(() => {
        setEvents([]);
        setSummaries([]);
      });
  }, []);

  const view = useMemo(() => {
    const byTicker = seasonEventByTicker(events ?? [], summaries ?? [], Q2_2026_WINDOW.start, Q2_2026_WINDOW.end);
    for (const ticker of Array.from(byTicker.keys())) if (!group.tickers.has(ticker)) byTicker.delete(ticker);
    const reported = Array.from(byTicker.values()).filter((event) => eventStatus(event) === "reported");
    const upcoming = Array.from(byTicker.values()).filter((event) => eventStatus(event) === "upcoming");
    const latestReports = (summaries ?? []).filter((row) => group.tickers.has(row.ticker)).slice(0, 10);
    const latestByTicker = new Map<string, PostEarningsSummary>();
    for (const row of latestReports) if (!latestByTicker.has(row.ticker)) latestByTicker.set(row.ticker, row);
    const uniqueLatest = Array.from(latestByTicker.values());
    const withConsensus = uniqueLatest.filter((row) => row.revenueActualUsd != null && row.revenueConsensusUsd != null);
    const beats = withConsensus.filter((row) => beatMiss(row.revenueActualUsd, row.revenueConsensusUsd) === "beat").length;
    const reactions = uniqueLatest.flatMap((row) => row.reactionPct == null ? [] : [row.reactionPct]);
    return {
      byTicker,
      reported: reported.length,
      upcoming: upcoming.length,
      datePending: group.tickers.size - byTicker.size,
      briefs: reported.filter((event) => briefCaptured(event, summaries ?? [])).length,
      latest: uniqueLatest,
      reportingPct: group.tickers.size ? Math.round((reported.length / group.tickers.size) * 100) : 0,
      beatRate: withConsensus.length ? Math.round((beats / withConsensus.length) * 100) : null,
      avgReaction: reactions.length ? reactions.reduce((sum, value) => sum + value, 0) / reactions.length : null,
    };
  }, [events, summaries, group]);

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-10 sm:px-8 sm:py-14">
      <header className="mb-7">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Coverage overviews</div>
        <div className="mt-2 flex items-center gap-3"><CoverageGroupIcon icon={group.icon} size={44} /><h1 className="text-[32px] font-extrabold tracking-tight text-[#15171c] dark:text-[#e7e8ea] sm:text-[40px]">{group.name}</h1></div>
        <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">{group.description}</p>
        <p className="mt-2 text-[11px] text-[#9a9ea8]">Includes {Array.from(group.tickers).map((ticker) => displayCompanyName(ticker, ticker)).join(" · ")}</p>
      </header>

      <div className="mb-7 flex gap-2 overflow-x-auto pb-1">
        {COVERAGE_GROUPS.map((item) => <button key={item.id} onClick={() => onSelectGroup(item.id)} className={`shrink-0 rounded-full border px-3 py-1.5 text-[12px] font-semibold transition-colors ${item.id === group.id ? "border-accent bg-accent-soft text-accent dark:bg-accent/20" : "border-black/[0.08] bg-white text-[#5b5f6b] dark:border-white/[0.1] dark:bg-[#121317] dark:text-[#9a9ea8]"}`}>{item.shortName}</button>)}
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <OverviewStat label="Constituents" value={String(group.tickers.size)} note="Tracked in this theme" />
        <OverviewStat label="Q2 reported" value={String(view.reported)} tone="up" />
        <OverviewStat label="Q2 upcoming" value={String(view.upcoming)} tone="pending" />
        <OverviewStat label="Briefs ready" value={String(view.briefs)} note={`${view.reportingPct}% reporting complete`} />
        <OverviewStat label="Revenue beat rate" value={view.beatRate == null ? "—" : `${view.beatRate}%`} />
        <OverviewStat label="Avg. reaction" value={view.avgReaction == null ? "—" : `${view.avgReaction >= 0 ? "+" : ""}${view.avgReaction.toFixed(1)}%`} tone={view.avgReaction == null ? undefined : view.avgReaction >= 0 ? "up" : "down"} />
      </div>

      <section className="mb-8">
        <div className="mb-3"><div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Reporting roster</div><div className="mt-1 text-[13px] text-[#9a9ea8]">Every constituent, with its current Q2 reporting status.</div></div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from(group.tickers).map((ticker) => {
            const event = view.byTicker.get(ticker);
            return <button key={ticker} onClick={() => onOpenCompany(ticker)} className="flex items-center gap-3 rounded-xl border border-black/[0.06] bg-white px-3 py-2.5 text-left hover:border-accent/35 dark:border-white/[0.08] dark:bg-[#121317]"><CompanyLogo ticker={ticker} company={event?.company ?? ticker} size={30} /><div className="min-w-0 flex-1"><div className="truncate text-[12px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{displayCompanyName(ticker, event?.company ?? ticker)}</div><div className="mt-0.5 font-mono text-[10px] text-[#9a9ea8]">{ticker}</div></div><TickerStatusChip ticker={ticker} event={event} /></button>;
          })}
        </div>
        {view.datePending > 0 && <div className="mt-2 text-[10px] text-[#9a9ea8]">{view.datePending} constituent{view.datePending === 1 ? "" : "s"} awaiting a confirmed Q2 calendar date.</div>}
      </section>

      <section>
        <div className="mb-3"><div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Completed briefs</div><div className="mt-1 text-[13px] text-[#9a9ea8]">Most recent captured report for each company in this group.</div></div>
        <div className="overflow-hidden rounded-card border border-black/[0.06] bg-white dark:border-white/[0.08] dark:bg-[#121317]">
          {summaries === null && <div className="px-5 py-12 text-center text-[13px] text-[#9a9ea8]">Loading reports…</div>}
          {summaries !== null && view.latest.length === 0 && <div className="px-5 py-12 text-center text-[13px] text-[#9a9ea8]">No completed briefs captured for this group yet.</div>}
          {view.latest.map((row, index) => {
            const verdict = beatMiss(row.revenueActualUsd, row.revenueConsensusUsd);
            return <button key={row._id} onClick={() => onOpenCompany(row.ticker)} className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.03] ${index ? "border-t border-black/[0.05] dark:border-white/[0.06]" : ""}`}><div className="flex min-w-0 items-center gap-3"><CompanyLogo ticker={row.ticker} company={row.company} size={34} /><div className="min-w-0"><div className="flex items-center gap-2"><span className="truncate text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{row.company}</span><span className="font-mono text-[11px] text-[#9a9ea8]">{row.ticker}</span></div><div className="mt-0.5 text-[11px] text-[#9a9ea8]">{relativeDay(row.reportDate)} · {row.reportTime} · Revenue {fmtUsdCompact(row.revenueActualUsd)}{row.revenueYoyPct != null ? ` · ${fmtPct(row.revenueYoyPct)} YoY` : ""}</div></div></div><div className="flex items-center gap-3">{verdict && <span className={`text-[10px] font-bold uppercase ${verdict === "beat" ? "text-emerald-600 dark:text-emerald-400" : verdict === "miss" ? "text-rose-600 dark:text-rose-400" : "text-[#8b8f99]"}`}>{verdict}</span>}<ReactionBadge pct={row.reactionPct} /></div></button>;
          })}
        </div>
      </section>
    </div>
  );
}

function OverviewStat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "up" | "down" | "pending" }) {
  return <div className="rounded-card border border-black/[0.06] bg-white p-4 dark:border-white/[0.08] dark:bg-[#121317]"><div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{label}</div><div className={`mt-1 text-[22px] font-bold tabular-nums ${tone === "up" ? "text-emerald-600 dark:text-emerald-400" : tone === "down" ? "text-rose-600 dark:text-rose-400" : tone === "pending" ? "text-amber-600 dark:text-amber-400" : "text-[#15171c] dark:text-[#e7e8ea]"}`}>{value}</div>{note && <div className="mt-0.5 text-[11px] text-[#9a9ea8]">{note}</div>}</div>;
}
