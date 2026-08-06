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
  const allSeries = indices
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
  const maxLen = Math.max(...allSeries.map((s) => s.pctSeries.length), 1);
  const xFor = (i: number) => (i / Math.max(maxLen - 1, 1)) * width;

  const firstT = allSeries[0]?.pctSeries[0]?.t;
  const firstPctSeries = allSeries[0]?.pctSeries;
  const lastT = firstPctSeries?.[firstPctSeries.length - 1]?.t;
  const fmtTime = (ms?: number) =>
    ms ? new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "";

  const hoverIdx =
    hoverX !== null ? Math.round((hoverX / width) * (maxLen - 1)) : null;

  return (
    <div className="mb-6 flex flex-col gap-4 rounded-card border border-black/[0.06] bg-white p-4 dark:border-white/[0.08] dark:bg-[#121317] sm:flex-row">
      <div className="flex shrink-0 flex-row gap-3 sm:flex-col sm:gap-2">
        {allSeries.map((idx) => {
          const up = (idx.changePct ?? 0) >= 0;
          return (
            <div key={idx.symbol} className="min-w-[128px]">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: COLORS[idx.symbol] }} />
                <span className="text-[11px] font-medium text-[#8b8f99]">{idx.name}</span>
              </div>
              <div className="mt-0.5 text-[15px] font-bold text-[#15171c] dark:text-[#e7e8ea]">
                {idx.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? "—"}
              </div>
              <div className={`text-[12px] font-semibold ${up ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
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
          className="h-[140px] w-full overflow-visible"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setHoverX(((e.clientX - rect.left) / rect.width) * width);
          }}
          onMouseLeave={() => setHoverX(null)}
        >
          {/* zero line */}
          <line x1={0} y1={height / 2} x2={width} y2={height / 2} stroke="currentColor" className="text-black/10 dark:text-white/10" strokeWidth={0.5} />
          {allSeries.map((idx) => {
            const d = idx.pctSeries
              .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(i)} ${yFor(p.pct)}`)
              .join(" ");
            return <path key={idx.symbol} d={d} fill="none" stroke={COLORS[idx.symbol]} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />;
          })}
          {hoverIdx !== null && (
            <line x1={xFor(hoverIdx)} y1={0} x2={xFor(hoverIdx)} y2={height} stroke="currentColor" className="text-black/20 dark:text-white/20" strokeWidth={0.5} />
          )}
        </svg>
        <div className="mt-1 flex justify-between text-[10px] text-[#9a9ea8]">
          <span>{fmtTime(firstT)}</span>
          <span>{fmtTime(lastT)}</span>
        </div>
        {hoverIdx !== null && (
          <div className="pointer-events-none absolute -top-1 right-0 rounded-md border border-black/10 bg-white px-2 py-1 text-[11px] shadow-sm dark:border-white/10 dark:bg-[#1c1d22]">
            <div className="mb-0.5 font-semibold text-[#8b8f99]">{fmtTime(allSeries[0]?.pctSeries[hoverIdx]?.t)}</div>
            {allSeries.map((idx) => (
              <div key={idx.symbol} className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: COLORS[idx.symbol] }} />
                <span className="font-medium">{idx.pctSeries[hoverIdx]?.pct.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
