import { useEffect, useMemo, useState } from "react";
import { listCalendarEvents, listRecentEarnings, type CalendarEvent, type PostEarningsSummary } from "../lib/convex";
import { COVERAGE_GROUPS } from "../lib/coverageGroups";
import { briefCaptured, eventStatus, FULL_2026_CALENDAR_WINDOW, Q2_2026_WINDOW, Q3_2026_WINDOW, seasonEventByTicker } from "../lib/earningsStatus";
import { fmtDate, fmtEps, fmtUsdCompact } from "../lib/format";
import { CompanyLogo } from "../components/CompanyLogo";

type Season = "q2" | "q3";
type StatusFilter = "all" | "reported" | "upcoming";
const CALENDAR_PAGE_SIZE = 100;

const SEASONS = {
  q2: { label: "Q2 2026 earnings", note: "Reports scheduled July–September", ...Q2_2026_WINDOW },
  q3: { label: "Q3 2026 anticipated", note: "Expected reports October–December", ...Q3_2026_WINDOW },
};

export function EarningsCalendar({ onOpenCompany }: { onOpenCompany: (ticker: string) => void }) {
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [summaries, setSummaries] = useState<PostEarningsSummary[]>([]);
  const [season, setSeason] = useState<Season>("q2");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [visibleLimit, setVisibleLimit] = useState(CALENDAR_PAGE_SIZE);

  useEffect(() => {
    Promise.all([
      listCalendarEvents(FULL_2026_CALENDAR_WINDOW.start, FULL_2026_CALENDAR_WINDOW.end),
      listRecentEarnings(250),
    ])
      .then(([calendarRows, summaryRows]) => {
        setEvents(calendarRows);
        setSummaries(summaryRows);
      })
      .catch(() => setEvents([]));
  }, []);

  const seasonDef = SEASONS[season];
  const view = useMemo(() => {
    const allSeasonRows = Array.from(seasonEventByTicker(events ?? [], summaries, seasonDef.start, seasonDef.end).values())
      .sort((a, b) => a.reportDate.localeCompare(b.reportDate) || a.company.localeCompare(b.company));
    const rows = allSeasonRows
      .filter((event) => statusFilter === "all" || eventStatus(event) === statusFilter)
      .filter((event) => {
        const needle = query.trim().toLowerCase();
        return !needle || event.ticker.toLowerCase().includes(needle) || event.company.toLowerCase().includes(needle);
      });
    const uniqueTickers = new Set(allSeasonRows.map((event) => event.ticker)).size;
    const reported = allSeasonRows.filter((event) => eventStatus(event) === "reported").length;
    const upcoming = allSeasonRows.filter((event) => eventStatus(event) === "upcoming").length;
    const captured = allSeasonRows.filter((event) => briefCaptured(event, summaries)).length;
    const confirmed = allSeasonRows.filter((event) => event.dateConfidence !== "inferred").length;
    const estimated = allSeasonRows.length - confirmed;
    return { rows, uniqueTickers, reported, upcoming, captured, confirmed, estimated };
  }, [events, seasonDef, statusFilter, query, summaries]);

  useEffect(() => {
    setVisibleLimit(CALENDAR_PAGE_SIZE);
  }, [query, season, statusFilter]);

  const visibleRows = view.rows.slice(0, visibleLimit);

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-6 sm:px-8 sm:py-14">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-5">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Coverage calendar</div>
          <h1 className="mt-2 text-[28px] font-extrabold tracking-tight text-[#15171c] dark:text-[#e7e8ea] sm:text-[40px]">Earnings Calendar</h1>
          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-[#5b5f6b] dark:text-[#9a9ea8]">
            Reported names, upcoming dates, and brief-capture status across the full coverage universe.
          </p>
        </div>
        <div className="flex w-full rounded-xl border border-black/[0.07] bg-white p-1 dark:border-white/[0.09] dark:bg-[#121317] sm:w-auto">
          {(Object.keys(SEASONS) as Season[]).map((key) => (
            <button key={key} onClick={() => setSeason(key)} className={`min-w-0 flex-1 rounded-lg px-2.5 py-2 text-left transition-colors sm:flex-none sm:px-3.5 ${season === key ? "bg-accent-soft text-accent dark:bg-accent/15" : "text-[#6f7480] dark:text-[#9a9ea8]"}`}>
              <div className="text-[12px] font-bold">{SEASONS[key].label}</div>
              <div className="mt-0.5 text-[10px] opacity-70">{SEASONS[key].note}</div>
            </button>
          ))}
        </div>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <CalendarStat label="Companies tracked" value={String(view.uniqueTickers)} note={`${view.confirmed} confirmed · ${view.estimated} estimated`} />
        <CalendarStat label="Reported" value={String(view.reported)} tone="reported" />
        <CalendarStat label="Upcoming" value={String(view.upcoming)} tone="upcoming" />
        <CalendarStat label="Briefs captured" value={String(view.captured)} note={view.reported ? `${Math.round((view.captured / view.reported) * 100)}% of reported` : "No reports yet"} />
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          {(["all", "reported", "upcoming"] as StatusFilter[]).map((status) => (
            <button key={status} onClick={() => setStatusFilter(status)} className={`rounded-full border px-3 py-1.5 text-[11px] font-semibold capitalize ${statusFilter === status ? "border-accent bg-accent-soft text-accent dark:bg-accent/15" : "border-black/[0.08] bg-white text-[#7a7f89] dark:border-white/[0.1] dark:bg-[#121317]"}`}>{status}</button>
          ))}
        </div>
        <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" placeholder="Search company or ticker…" className="w-full rounded-lg border border-black/[0.08] bg-white px-3 py-2 text-[12px] outline-none focus:border-accent dark:border-white/[0.1] dark:bg-[#121317] sm:w-64" />
      </div>

      <div className="space-y-2 md:hidden">
        {events === null && <div className="rounded-card border border-black/[0.06] bg-white px-4 py-10 text-center text-[13px] text-[#9a9ea8] dark:border-white/[0.08] dark:bg-[#121317]">Loading calendar…</div>}
        {events !== null && view.rows.length === 0 && <div className="rounded-card border border-black/[0.06] bg-white px-4 py-10 text-center text-[13px] text-[#9a9ea8] dark:border-white/[0.08] dark:bg-[#121317]">No calendar events match this view.</div>}
        {visibleRows.map((event) => {
          const status = eventStatus(event);
          const captured = briefCaptured(event, summaries);
          const themes = COVERAGE_GROUPS.filter((group) => group.tickers.has(event.ticker)).map((group) => group.shortName);
          return (
            <button key={`mobile:${event.ticker}:${event.reportDate}`} onClick={() => onOpenCompany(event.ticker)} className="w-full rounded-card border border-black/[0.06] bg-white p-3.5 text-left dark:border-white/[0.08] dark:bg-[#121317]">
              <div className="flex items-start gap-3">
                <CompanyLogo ticker={event.ticker} company={event.company} size={34} />
                <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{event.company}</div><div className="mt-0.5 font-mono text-[10px] text-[#9a9ea8]">{event.ticker} · {calendarDateLabel(event)}</div></div>
                <span className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-bold ${status === "reported" ? "bg-emerald-500/[0.1] text-emerald-700 dark:text-emerald-300" : "bg-amber-500/[0.1] text-amber-700 dark:text-amber-300"}`}>{status === "reported" ? "Reported" : "Upcoming"}</span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 border-t border-black/[0.05] pt-2.5 text-[10px] dark:border-white/[0.06]"><div><span className="text-[#9a9ea8]">Brief</span><div className="mt-0.5 font-medium text-[#5b5f6b] dark:text-[#c4c7ce]">{status === "reported" ? captured ? "Ready" : "Pending" : "After report"}</div></div><div><span className="text-[#9a9ea8]">Estimate</span><div className="mt-0.5 font-mono text-[#5b5f6b] dark:text-[#c4c7ce]">{event.epsEstimate == null ? "EPS —" : `EPS ${fmtEps(event.epsEstimate)}`}</div></div></div>
              <div className="mt-2 truncate text-[9px] text-[#9a9ea8]">{themes.length ? themes.join(" · ") : "Broad coverage"}</div>
            </button>
          );
        })}
      </div>

      <div className="hidden overflow-x-auto rounded-card border border-black/[0.06] bg-white dark:border-white/[0.08] dark:bg-[#121317] md:block">
        <table className="w-full min-w-[920px] border-collapse text-left">
          <thead className="border-b border-black/[0.06] bg-black/[0.015] dark:border-white/[0.07] dark:bg-white/[0.02]">
            <tr>{["Date", "Company", "Status", "Coverage themes", "EPS estimate", "Revenue estimate"].map((heading) => <th key={heading} className="px-4 py-3 text-[10px] font-bold uppercase tracking-[0.1em] text-[#8b8f99]">{heading}</th>)}</tr>
          </thead>
          <tbody>
            {events === null && <tr><td colSpan={6} className="px-4 py-12 text-center text-[13px] text-[#9a9ea8]">Loading calendar…</td></tr>}
            {events !== null && view.rows.length === 0 && <tr><td colSpan={6} className="px-4 py-12 text-center text-[13px] text-[#9a9ea8]">No calendar events match this view.</td></tr>}
            {visibleRows.map((event, index) => {
              const status = eventStatus(event);
              const captured = briefCaptured(event, summaries);
              const themes = COVERAGE_GROUPS.filter((group) => group.tickers.has(event.ticker)).map((group) => group.shortName);
              return (
                <tr key={`${event.ticker}:${event.reportDate}`} className={index ? "border-t border-black/[0.05] dark:border-white/[0.06]" : ""}>
                  <td className="whitespace-nowrap px-4 py-3"><div className="text-[12px] font-semibold text-[#2b2e35] dark:text-[#dcdee2]">{calendarDateLabel(event)}</div><div className="mt-0.5 text-[10px] text-[#9a9ea8]">{calendarDateNote(event)}</div></td>
                  <td className="px-4 py-3"><button onClick={() => onOpenCompany(event.ticker)} className="flex items-center gap-2.5 text-left hover:underline"><CompanyLogo ticker={event.ticker} company={event.company} size={30} /><span><span className="block text-[12px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{event.company}</span><span className="font-mono text-[10px] text-[#9a9ea8]">{event.ticker}</span></span></button></td>
                  <td className="px-4 py-3"><span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold ${status === "reported" ? "bg-emerald-500/[0.1] text-emerald-700 dark:text-emerald-300" : "bg-amber-500/[0.1] text-amber-700 dark:text-amber-300"}`}>{status === "reported" ? "Reported" : "Upcoming"}</span><div className="mt-1 text-[9px] text-[#9a9ea8]">{status === "reported" ? captured ? "Brief ready" : "Brief pending" : "Anticipated date"}</div></td>
                  <td className="max-w-[260px] px-4 py-3 text-[10px] text-[#7a7f89] dark:text-[#9a9ea8]">{themes.length ? themes.join(" · ") : "Broad coverage"}</td>
                  <td className="px-4 py-3 font-mono text-[11px] text-[#2b2e35] dark:text-[#dcdee2]">{event.epsEstimate == null ? "—" : fmtEps(event.epsEstimate)}</td>
                  <td className="px-4 py-3 font-mono text-[11px] text-[#2b2e35] dark:text-[#dcdee2]">{fmtUsdCompact(event.revenueEstimateUsd ?? null)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {visibleRows.length < view.rows.length && (
        <div className="mt-4 text-center">
          <p className="mb-2 text-[11px] text-[#9a9ea8]">
            Showing {visibleRows.length.toLocaleString()} of {view.rows.length.toLocaleString()} matching companies.
          </p>
          <button
            type="button"
            onClick={() => setVisibleLimit((limit) => Math.min(limit + CALENDAR_PAGE_SIZE, view.rows.length))}
            className="rounded-lg border border-black/[0.08] bg-white px-4 py-2 text-[12px] font-semibold text-[#5b5f6b] hover:border-accent/40 hover:text-accent dark:border-white/[0.1] dark:bg-[#121317] dark:text-[#b8bbc3]"
          >
            Show {Math.min(CALENDAR_PAGE_SIZE, view.rows.length - visibleRows.length).toLocaleString()} more
          </button>
        </div>
      )}
    </div>
  );
}

function CalendarStat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "reported" | "upcoming" }) {
  return <div className="rounded-card border border-black/[0.06] bg-white p-4 dark:border-white/[0.08] dark:bg-[#121317]"><div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{label}</div><div className={`mt-1 text-[24px] font-bold tabular-nums ${tone === "reported" ? "text-emerald-600 dark:text-emerald-400" : tone === "upcoming" ? "text-amber-600 dark:text-amber-400" : "text-[#15171c] dark:text-[#e7e8ea]"}`}>{value}</div>{note && <div className="mt-0.5 text-[10px] text-[#9a9ea8]">{note}</div>}</div>;
}

function calendarDateLabel(event: CalendarEvent) {
  if (event.dateConfidence !== "inferred") return fmtDate(event.reportDate);
  return event.reportTime.startsWith("Estimated") ? `Est. ${fmtDate(event.reportDate)}` : "Earlier in Q2";
}

function calendarDateNote(event: CalendarEvent) {
  if (event.dateConfidence !== "inferred") return event.reportTime;
  return event.reportTime.startsWith("Estimated") ? "Prior-quarter cadence; confirmation pending" : "Exact date backfill pending";
}
