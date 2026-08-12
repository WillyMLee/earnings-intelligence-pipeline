// Mirrors the formatting conventions in the pipeline's own
// earnings_workflows_common/financial_stat_grid.py, so a number reads the
// same way here as it does in the email briefs this dashboard is fed by.

export function fmtUsdCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const absolute = Math.abs(value);
  const billions = absolute / 1_000_000_000;
  if (billions >= 1) return `${sign}$${billions.toLocaleString(undefined, { maximumFractionDigits: 2 })}B`;
  const millions = absolute / 1_000_000;
  return `${sign}$${millions.toLocaleString(undefined, { maximumFractionDigits: 0 })}M`;
}

export function fmtPct(value: number | null | undefined, signed = true): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function fmtEps(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value < 0 ? `-$${Math.abs(value).toFixed(2)}` : `$${value.toFixed(2)}`;
}

export function fmtDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function relativeDay(iso: string): string {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${iso}T00:00:00`);
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === -1) return "Yesterday";
  if (diffDays > 0 && diffDays <= 6) return target.toLocaleDateString(undefined, { weekday: "long" });
  return fmtDate(iso);
}

/** Beat/miss verdict from an actual-vs-consensus pair, used to color a
 * badge. Returns null when there's nothing to compare (no consensus
 * available) -- callers should render a neutral state, not guess. */
export function beatMiss(actual: number | null, consensus: number | null): "beat" | "miss" | "inline" | null {
  if (actual === null || consensus === null || !consensus) return null;
  const diffPct = ((actual - consensus) / Math.abs(consensus)) * 100;
  if (Math.abs(diffPct) < 0.5) return "inline";
  return diffPct > 0 ? "beat" : "miss";
}
