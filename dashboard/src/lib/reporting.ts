import type { PostEarningsSummary } from "./convex";

function reportTimeRank(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized.includes("after") || normalized === "amc") return 3;
  if (normalized.includes("before") || normalized === "bmo") return 2;
  return 1;
}

export function sortByReportTiming(rows: PostEarningsSummary[]) {
  return rows.slice().sort((left, right) => {
    const byDate = right.reportDate.localeCompare(left.reportDate);
    if (byDate !== 0) return byDate;
    const bySession = reportTimeRank(right.reportTime) - reportTimeRank(left.reportTime);
    if (bySession !== 0) return bySession;
    return right.updatedAt.localeCompare(left.updatedAt);
  });
}

export function cycleCutoff(days = 45) {
  const cutoff = new Date();
  cutoff.setHours(0, 0, 0, 0);
  cutoff.setDate(cutoff.getDate() - days);
  return cutoff.toISOString().slice(0, 10);
}

export function currentWeekWindow() {
  const today = new Date();
  const day = today.getDay();
  const monday = new Date(today);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(today.getDate() - ((day + 6) % 7));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const iso = (value: Date) => {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const date = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${date}`;
  };
  return { start: iso(monday), end: iso(sunday) };
}

export function isReviewWarning(text?: string | null) {
  return /^\s*(note|warning|caveat)\s*:/i.test(String(text ?? ""));
}

export function bestHighlight(summary: PostEarningsSummary) {
  const bullets = summary.financialHighlights ?? [];
  const preferred = bullets.find((bullet) => !isReviewWarning(bullet.text));
  return preferred?.text ?? summary.keyMetrics.find((metric) => !isReviewWarning(metric)) ?? "";
}
