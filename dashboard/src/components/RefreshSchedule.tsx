import type { CalendarEvent, PostEarningsSummary } from "../lib/convex";

type UtcSchedule = { days: number[]; hour: number; minute: number };
type RefreshJob = {
  title: string;
  cadence: string;
  detail: string;
  schedules: UtcSchedule[];
};

const WEEKDAYS = [1, 2, 3, 4, 5];

const ACTIVE_JOBS: RefreshJob[] = [
  {
    title: "Input prefetch",
    cadence: "Weekdays · 12:00 UTC",
    detail: "Refreshes the calendar and captures consensus for the next 21 days, up to 150 names per run.",
    schedules: [{ days: WEEKDAYS, hour: 12, minute: 0 }],
  },
  {
    title: "Pre-earnings briefs",
    cadence: "Weekdays · 13:30 UTC",
    detail: "Builds company context for the email universe and dashboard-only coverage before reports.",
    schedules: [{ days: WEEKDAYS, hour: 13, minute: 30 }],
  },
  {
    title: "Post-earnings briefs",
    cadence: "Weekdays · 13:30 and 22:00 UTC",
    detail: "Processes before-open results near the open and after-close results in the evening.",
    schedules: [
      { days: WEEKDAYS, hour: 13, minute: 30 },
      { days: WEEKDAYS, hour: 22, minute: 0 },
    ],
  },
  {
    title: "Sunday radar",
    cadence: "Sundays · 21:00 UTC",
    detail: "Refreshes the upcoming Monday–Friday earnings preview and its financial snapshots.",
    schedules: [{ days: [0], hour: 21, minute: 0 }],
  },
];

const PLANNED_JOBS = [
  {
    title: "Transcript-history backfill",
    target: "Target cadence: nightly during the initial backfill, then on report days.",
    detail: "The resumable worker exists, but it is not attached to a production cron yet.",
  },
  {
    title: "Q1 2020+ SEC actuals and company profiles",
    target: "Target cadence: nightly fact batches; weekly profile batches for changed source packets.",
    detail: "Still in the planned data project, so there is no committed production run time yet.",
  },
];

function nextUtcRun(schedule: UtcSchedule, now: Date) {
  for (let offset = 0; offset <= 14; offset += 1) {
    const candidate = new Date(Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + offset,
      schedule.hour,
      schedule.minute,
    ));
    if (candidate > now && schedule.days.includes(candidate.getUTCDay())) return candidate;
  }
  return null;
}

function nextJobRun(job: RefreshJob, now: Date) {
  return job.schedules
    .map((schedule) => nextUtcRun(schedule, now))
    .filter((value): value is Date => value !== null)
    .sort((left, right) => left.getTime() - right.getTime())[0] ?? null;
}

function formatEastern(value: Date, includeDate = true) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    ...(includeDate ? { weekday: "short", month: "short", day: "numeric" } : {}),
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(value);
}

function latestTimestamp(values: Array<string | undefined | null>) {
  const timestamps = values
    .map((value) => value ? new Date(value).getTime() : Number.NaN)
    .filter(Number.isFinite);
  return timestamps.length ? new Date(Math.max(...timestamps)) : null;
}

export function RefreshSchedule({
  summaries,
  events,
}: {
  summaries: PostEarningsSummary[] | null;
  events: CalendarEvent[] | null;
}) {
  const now = new Date();
  const nextRuns = ACTIVE_JOBS
    .map((job) => ({ job, next: nextJobRun(job, now) }))
    .filter((entry): entry is { job: RefreshJob; next: Date } => entry.next !== null)
    .sort((left, right) => left.next.getTime() - right.next.getTime());
  const nextOverall = nextRuns[0];
  const lastBriefRefresh = latestTimestamp((summaries ?? []).map((row) => row.updatedAt));
  const lastCalendarRefresh = latestTimestamp((events ?? []).map((row) => row.updatedAt));
  const lastDataRefresh = latestTimestamp([
    lastBriefRefresh?.toISOString(),
    lastCalendarRefresh?.toISOString(),
  ]);

  return (
    <details className="group mb-6 rounded-card border border-black/[0.06] bg-white dark:border-white/[0.08] dark:bg-[#121317]">
      <summary className="flex cursor-pointer list-none flex-col gap-2 px-4 py-3.5 [&::-webkit-details-marker]:hidden sm:flex-row sm:items-center sm:justify-between sm:gap-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8b8f99]">Data refresh schedule</span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-label="Scheduled jobs configured" />
          </div>
          <div className="mt-1 text-[12px] text-[#5b5f6b] dark:text-[#b2b6bf]">
            Next scheduled batch{nextOverall ? <> · <span className="font-semibold text-[#15171c] dark:text-[#e7e8ea]">{nextOverall.job.title}</span> · {formatEastern(nextOverall.next)}</> : " unavailable"}
          </div>
        </div>
        <div className="flex items-center justify-between gap-4 sm:justify-end">
          <div className="text-left sm:text-right">
            <div className="text-[9px] font-semibold uppercase tracking-wide text-[#9a9ea8]">Latest stored update</div>
            <div className="mt-0.5 text-[11px] font-medium text-[#5b5f6b] dark:text-[#b2b6bf]">{lastDataRefresh ? formatEastern(lastDataRefresh) : summaries === null || events === null ? "Loading…" : "Not available"}</div>
          </div>
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-black/[0.07] text-[15px] text-[#8b8f99] transition-transform group-open:rotate-45 dark:border-white/[0.09]">+</span>
        </div>
      </summary>

      <div className="border-t border-black/[0.06] px-4 py-4 dark:border-white/[0.07]">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {nextRuns.map(({ job, next }) => (
            <div key={job.title} className="rounded-xl border border-black/[0.05] bg-black/[0.015] p-3 dark:border-white/[0.06] dark:bg-white/[0.02]">
              <div className="flex items-start justify-between gap-2">
                <div className="text-[12px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{job.title}</div>
                <span className="shrink-0 rounded-full bg-emerald-500/[0.1] px-2 py-0.5 text-[9px] font-bold uppercase text-emerald-700 dark:text-emerald-300">Scheduled</span>
              </div>
              <div className="mt-1 font-mono text-[10px] text-[#7a7f89] dark:text-[#9a9ea8]">{job.cadence}</div>
              <div className="mt-2 text-[11px] font-semibold text-accent">Next · {formatEastern(next)}</div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[#8b8f99]">{job.detail}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 grid gap-3 border-t border-black/[0.05] pt-4 dark:border-white/[0.06] sm:grid-cols-2">
          {PLANNED_JOBS.map((job) => (
            <div key={job.title} className="flex min-w-0 gap-3">
              <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-[#b8bbc2] dark:bg-[#5d616b]" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><span className="text-[11px] font-semibold text-[#5b5f6b] dark:text-[#c4c7ce]">{job.title}</span><span className="text-[9px] font-bold uppercase text-[#9a9ea8]">Planned · not active</span></div>
                <div className="mt-0.5 text-[10px] text-[#7a7f89] dark:text-[#9a9ea8]">{job.target}</div>
                <div className="mt-0.5 text-[10px] leading-relaxed text-[#9a9ea8]">{job.detail}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-[#9a9ea8]">
          <span>Calendar store · {lastCalendarRefresh ? formatEastern(lastCalendarRefresh) : "Not available"}</span>
          <span>Brief archive · {lastBriefRefresh ? formatEastern(lastBriefRefresh) : "Not available"}</span>
          <span>Configured schedules are stored in UTC; next runs are converted to New York time.</span>
        </div>
      </div>
    </details>
  );
}
