import { useEffect, useRef, useState } from "react";

type IndexPoint = { t: number; price: number };
type IndexSeries = {
  symbol: string;
  name: string;
  price: number | null;
  previousClose: number | null;
  change: number | null;
  changePct: number | null;
  series: IndexPoint[];
};

// Fixed categorical order, one hue each -- never cycled/reassigned by
// filter state (there's no filter here, but the fixed-order convention
// stays consistent with the rest of the app's charts).
const COLORS: Record<string, string> = {
  "^DJI": "#ec4899", // Dow -- pink
  "^GSPC": "#3b82f6", // S&P 500 -- blue
  "^IXIC": "#10b981", // Nasdaq -- teal
};

async function fetchIndices(): Promise<IndexSeries[]> {
  const res = await fetch("/api/indices");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const payload = await res.json();
  return payload.indices as IndexSeries[];
}

export function IndexBar() {
  const [indices, setIndices] = useState<IndexSeries[] | null>(null);
  const [error, setError] = useState("");
  const [hoverX, setHoverX] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchIndices()
        .then((data) => !cancelled && setIndices(data))
        .catch((err: Error) => !cancelled && setError(err.message));
    };
    load();
    // 60s poll -- intraday 5-minute-bar data doesn't move fast enough to
    // justify tighter polling, and the Worker itself caches for 15s.
    const interval = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (error) return null; // non-fatal -- the rest of the dashboard works without this
  if (!indices) {
    return (
      <div className="mb-6 h-[132px] animate-pulse rounded-card border border-black/[0.06] bg-black/[0.02] dark:border-white/[0.08] dark:bg-white/[0.02]" />
    );
  }

  // Index every series to % change from ITS OWN first point -- three
  // indices of wildly different absolute scale (Dow ~54k, S&P ~7.7k,
  // Nasdaq ~26k) can only share one y-axis this way; per the dataviz
  // skill, this is the correct move instead of a dual/triple axis chart.
  const easternMinutes = (ms: number) => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "numeric",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(new Date(ms));
    const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0) % 24;
    const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
    return hour * 60 + minute;
  };
  const marketOpen = 9 * 60 + 30;
  const marketClose = 16 * 60;
  const xForTime = (ms: number) => Math.max(0, Math.min(100, ((easternMinutes(ms) - marketOpen) / (marketClose - marketOpen)) * 100));

  const allSeries = indices
    .map((idx) => ({ ...idx, series: idx.series.filter((point) => easternMinutes(point.t) >= marketOpen && easternMinutes(point.t) <= marketClose) }))
    .filter((idx) => idx.series.length > 0)
    .map((idx) => {
      const base = idx.series[0].price;
      return {
        ...idx,
        pctSeries: idx.series.map((p) => ({ t: p.t, pct: ((p.price - base) / base) * 100 })),
      };
    });

  const width = 100;
  const height = 140;
  const allPcts = allSeries.flatMap((s) => s.pctSeries.map((p) => p.pct));
  const maxAbs = Math.max(...allPcts.map((v) => Math.abs(v)), 0.1);
  const yFor = (pct: number) => height / 2 - (pct / maxAbs) * (height / 2 - 12);
  const fmtTime = (ms?: number) => ms ? new Date(ms).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }) : "";
  const reference = allSeries[0]?.pctSeries ?? [];
  const hoverIdx = hoverX === null || reference.length === 0
    ? null
    : reference.reduce((best, point, index) => Math.abs(xForTime(point.t) - hoverX) < Math.abs(xForTime(reference[best].t) - hoverX) ? index : best, 0);
  const nearestPct = (series: { t: number; pct: number }[], target?: number) => {
    if (target == null || series.length === 0) return null;
    return series.reduce((best, point) => Math.abs(point.t - target) < Math.abs(best.t - target) ? point : best, series[0]);
  };

  return (
    <div className="mb-6 flex flex-col gap-3 rounded-card border border-black/[0.06] bg-white p-3 dark:border-white/[0.08] dark:bg-[#121317] sm:flex-row sm:gap-4 sm:p-4">
      <div className="grid shrink-0 grid-cols-3 gap-2 sm:flex sm:flex-col">
        {allSeries.map((idx) => {
          const up = (idx.changePct ?? 0) >= 0;
          return (
            <div key={idx.symbol} className="min-w-0 sm:min-w-[128px]">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: COLORS[idx.symbol] }} />
                <span className="truncate text-[9px] font-medium text-[#8b8f99] sm:text-[11px]">{idx.name}</span>
              </div>
              <div className="mt-0.5 truncate text-[13px] font-bold text-[#15171c] dark:text-[#e7e8ea] sm:text-[15px]">
                {idx.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? "—"}
              </div>
              <div className={`truncate text-[10px] font-semibold sm:text-[12px] ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                {idx.change !== null ? `${up ? "+" : ""}${idx.change.toFixed(2)}` : "—"}{" "}
                {idx.changePct !== null ? `${up ? "+" : ""}${idx.changePct.toFixed(2)}%` : ""}
              </div>
            </div>
          );
        })}
      </div>

      <div className="relative min-w-0 flex-1">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-[110px] w-full overflow-visible sm:h-[140px]"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setHoverX(((e.clientX - rect.left) / rect.width) * width);
          }}
          onMouseLeave={() => setHoverX(null)}
        >
          {/* zero line */}
          <line x1={0} y1={height / 2} x2={width} y2={height / 2} stroke="currentColor" className="text-black/20 dark:text-white/20" strokeWidth={0.65} />
          {allSeries.map((idx) => {
            const d = idx.pctSeries
              .map((p, i) => `${i === 0 ? "M" : "L"} ${xForTime(p.t)} ${yFor(p.pct)}`)
              .join(" ");
            return <path key={idx.symbol} d={d} fill="none" stroke={COLORS[idx.symbol]} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />;
          })}
          {hoverIdx !== null && (
            <line x1={xForTime(reference[hoverIdx].t)} y1={0} x2={xForTime(reference[hoverIdx].t)} y2={height} stroke="currentColor" className="text-black/20 dark:text-white/20" strokeWidth={0.5} />
          )}
        </svg>
        <div className="mt-1 grid grid-cols-4 text-[10px] text-[#9a9ea8]">
          <span>9:30 AM</span>
          <span className="text-center">12 PM</span>
          <span className="text-center">2 PM</span>
          <span className="text-right">4 PM close</span>
        </div>
        {hoverIdx !== null && (
          <div className="pointer-events-none absolute -top-1 right-0 rounded-md border border-black/10 bg-white px-2 py-1 text-[11px] shadow-sm dark:border-white/10 dark:bg-[#1c1d22]">
            <div className="mb-0.5 font-semibold text-[#8b8f99]">{fmtTime(reference[hoverIdx]?.t)} ET</div>
            {allSeries.map((idx) => {
              const point = nearestPct(idx.pctSeries, reference[hoverIdx]?.t);
              return <div key={idx.symbol} className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: COLORS[idx.symbol] }} />
                <span className="font-medium">{point?.pct.toFixed(2)}%</span>
              </div>;
            })}
          </div>
        )}
      </div>
    </div>
  );
}
