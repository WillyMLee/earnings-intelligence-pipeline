import type { CalendarEvent, PostEarningsSummary } from "./convex";

export type EarningsStatus = "reported" | "upcoming" | "unscheduled";

export const Q2_2026_WINDOW = { start: "2026-07-01", end: "2026-09-30" };
export const Q3_2026_WINDOW = { start: "2026-10-01", end: "2026-12-31" };
export const FULL_2026_CALENDAR_WINDOW = { start: Q2_2026_WINDOW.start, end: Q3_2026_WINDOW.end };

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
  summaries: PostEarningsSummary[],
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
    });
  }
  return byTicker;
}

export function briefCaptured(event: CalendarEvent, summaries: PostEarningsSummary[]): boolean {
  return summaries.some((summary) => summary.ticker === event.ticker && summary.reportDate === event.reportDate);
}
