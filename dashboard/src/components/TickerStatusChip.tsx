import type { CalendarEvent } from "../lib/convex";
import { eventStatus } from "../lib/earningsStatus";
import { fmtDate } from "../lib/format";

export function TickerStatusChip({ ticker, event, compact = false }: { ticker: string; event?: CalendarEvent; compact?: boolean }) {
  const status = eventStatus(event);
  const styles = {
    reported: "border-emerald-500/25 bg-emerald-500/[0.08] text-emerald-700 dark:text-emerald-300",
    upcoming: "border-amber-500/30 bg-amber-500/[0.08] text-amber-700 dark:text-amber-300",
    unscheduled: "border-black/[0.08] bg-black/[0.02] text-[#8b8f99] dark:border-white/[0.08] dark:bg-white/[0.03]",
  }[status];
  const label = status === "reported" ? "Reported" : status === "upcoming" ? "Upcoming" : "Date pending";

  return (
    <span
      title={`${ticker} · ${label}${event ? ` · ${fmtDate(event.reportDate)} ${event.reportTime}` : ""}`}
      className={`inline-flex items-center gap-1.5 rounded-md border font-mono font-semibold ${styles} ${compact ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-1 text-[10px]"}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${status === "reported" ? "bg-emerald-500" : status === "upcoming" ? "bg-amber-500" : "bg-[#a0a4ad]"}`} />
      {compact ? ticker : label}
      {!compact && event && <span className="font-sans font-normal opacity-70">{new Date(`${event.reportDate}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
    </span>
  );
}
