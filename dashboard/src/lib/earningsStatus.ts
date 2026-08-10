import type { CalendarEvent, PostEarningsSummary } from "./convex";

export type EarningsStatus = "reported" | "upcoming" | "unscheduled";

export const Q2_2026_WINDOW = { start: "2026-07-01", end: "2026-09-30" };
export const Q3_2026_WINDOW = { start: "2026-10-01", end: "2026-12-31" };
export const FULL_2026_CALENDAR_WINDOW = { start: Q2_2026_WINDOW.start, end: Q3_2026_WINDOW.end };

const VERIFIED_Q2_2026_REPORTS: CalendarEvent[] = [
  // Official IR dates retained because the rolling provider feed no longer
  // includes these completed rows:
  // Alphabet: https://abc.xyz/investor/ (Q2 2026 call, July 22)
  // Tesla: https://ir.tesla.com/press-release/tesla-releases-second-quarter-2026-financial-results
  // DoorDash: https://ir.doordash.com/events-and-presentations/events-calendar/event-details/2026/DoorDash-Q2-2026-Earnings-Call/default.aspx
  // Airbnb: https://investors.airbnb.com/press-releases/news-details/2026/Airbnb-to-Announce-Second-Quarter-2026-Results/default.aspx
  { ticker: "GOOGL", company: "Alphabet", reportDate: "2026-07-22", reportTime: "After Close", dateConfidence: "confirmed" },
  { ticker: "TSLA", company: "Tesla", reportDate: "2026-07-22", reportTime: "After Close", dateConfidence: "confirmed" },
  { ticker: "DASH", company: "DoorDash", reportDate: "2026-08-05", reportTime: "After Close", dateConfidence: "confirmed" },
  { ticker: "ABNB", company: "Airbnb", reportDate: "2026-08-06", reportTime: "After Close", dateConfidence: "confirmed" },
];

type CompletedReport = Pick<PostEarningsSummary, "ticker" | "company" | "reportDate" | "reportTime" | "sector">;

export function todayIso(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function eventStatus(event: CalendarEvent | undefined, today = todayIso()): EarningsStatus {
  if (!event) return "unscheduled";
  return event.reportDate <= today ? "reported" : "upcoming";
}

export function latestEventByTicker(events: CalendarEvent[]): Map<string, CalendarEvent> {
  const today = todayIso();
  const byTicker = new Map<string, CalendarEvent>();
  for (const event of events) {
    const prior = byTicker.get(event.ticker);
    if (!prior) {
      byTicker.set(event.ticker, event);
      continue;
    }
    const eventIsFuture = event.reportDate > today;
    const priorIsFuture = prior.reportDate > today;
    if ((eventIsFuture && !priorIsFuture) || (eventIsFuture === priorIsFuture && event.reportDate < prior.reportDate)) {
      byTicker.set(event.ticker, event);
    }
  }
  return byTicker;
}

export function seasonEventByTicker(
  events: CalendarEvent[],
  summaries: CompletedReport[],
  start: string,
  end: string,
): Map<string, CalendarEvent> {
  const byTicker = latestEventByTicker(
    events.filter((event) => event.reportDate >= start && event.reportDate <= end),
  );
  for (const summary of summaries) {
    if (summary.reportDate < start || summary.reportDate > end) continue;
    byTicker.set(summary.ticker, {
      ticker: summary.ticker,
      company: summary.company,
      reportDate: summary.reportDate,
      reportTime: summary.reportTime,
      sector: summary.sector,
      dateConfidence: "confirmed",
    });
  }

  if (start === Q2_2026_WINDOW.start && end === Q2_2026_WINDOW.end) {
    for (const verified of VERIFIED_Q2_2026_REPORTS) byTicker.set(verified.ticker, verified);

    // Some calendar providers stop returning rows once the report date has
    // passed. A confirmed Q3 date proves the preceding Q2 reporting event is
    // complete even when that old row has fallen out of the feed. Keep it
    // reported while clearly withholding an unverified exact date.
    for (const nextQuarter of events) {
      if (nextQuarter.reportDate < Q3_2026_WINDOW.start || nextQuarter.reportDate > Q3_2026_WINDOW.end) continue;
      if (byTicker.has(nextQuarter.ticker)) continue;
      byTicker.set(nextQuarter.ticker, {
        ticker: nextQuarter.ticker,
        company: nextQuarter.company,
        reportDate: start,
        reportTime: "Date backfill pending",
        sector: nextQuarter.sector,
        dateConfidence: "inferred",
      });
    }
  }

  if (start === Q3_2026_WINDOW.start && end === Q3_2026_WINDOW.end) {
    // The provider's forward calendar is intentionally sparse several weeks
    // out. Keep every currently tracked company visible by projecting its Q2
    // date forward one quarter. A provider-supplied Q3 row always wins and
    // projected dates remain explicitly labelled as estimates in the UI.
    const priorQuarter = seasonEventByTicker(
      events,
      summaries,
      Q2_2026_WINDOW.start,
      Q2_2026_WINDOW.end,
    );
    for (const prior of priorQuarter.values()) {
      if (byTicker.has(prior.ticker)) continue;
      const projectedDate = addUtcDays(prior.reportDate, 91);
      if (projectedDate < start || projectedDate > end) continue;
      byTicker.set(prior.ticker, {
        ticker: prior.ticker,
        company: prior.company,
        reportDate: projectedDate,
        reportTime: "Estimated from prior-quarter cadence",
        sector: prior.sector,
        dateConfidence: "inferred",
      });
    }
  }
  return byTicker;
}

function addUtcDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function briefCaptured(event: CalendarEvent, summaries: PostEarningsSummary[]): boolean {
  return summaries.some((summary) => summary.ticker === event.ticker && summary.reportDate === event.reportDate);
}
