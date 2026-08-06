import { useState } from "react";
import { fmtUsdCompact } from "../lib/format";

type Point = { label: string; value: number | null };

/**
 * A single-series magnitude-over-time chart, one metric per instance
 * (never dual-axis -- two measures of different scale get two separate
 * charts, per the dataviz skill). Plain SVG, no charting library: this
 * pipeline only recently started archiving structured history, so most
 * tickers will have a handful of points at most -- a lightweight custom
 * bar chart handles that better than a general-purpose charting lib would.
 */
export function TrendChart({ title, points, accent = "#e8724c" }: { title: string; points: Point[]; accent?: string }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const withData = points.filter((p) => p.value !== null) as { label: string; value: number }[];

  if (withData.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-black/10 px-4 py-8 text-center text-[12px] text-[#9a9ea8] dark:border-white/10">
        No {title.toLowerCase()} data archived yet.
      </div>
    );
  }
  if (withData.length === 1) {
    return (
      <div className="rounded-xl border border-black/[0.06] bg-black/[0.02] px-4 py-6 dark:border-white/[0.08] dark:bg-white/[0.02]">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{title}</div>
        <div className="mt-1 text-[20px] font-bold text-[#15171c] dark:text-[#e7e8ea]">
          {fmtUsdCompact(withData[0].value)}
        </div>
        <div className="mt-1 text-[11px] text-[#9a9ea8]">
          {withData[0].label} · trend builds up as more quarters are archived
        </div>
      </div>
    );
  }

  const max = Math.max(...withData.map((p) => Math.abs(p.value)), 1);
  const height = 120;
  const barWidth = 100 / withData.length;

  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99] dark:text-[#7d818c]">
        {title}
      </div>
      <div className="relative">
        <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="h-[120px] w-full overflow-visible">
          {withData.map((p, i) => {
            const barHeight = (Math.abs(p.value) / max) * (height - 24);
            const x = i * barWidth + barWidth * 0.2;
            const w = barWidth * 0.6;
            const y = height - 20 - barHeight;
            return (
              <g key={i} onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}>
                <rect x={x} y={y} width={w} height={Math.max(barHeight, 2)} rx={1.5} fill={accent} opacity={hovered === i ? 1 : 0.75} />
              </g>
            );
          })}
        </svg>
        {hovered !== null && (
          <div className="pointer-events-none absolute -top-1 left-0 rounded-md border border-black/10 bg-white px-2 py-1 text-[11px] font-semibold shadow-sm dark:border-white/10 dark:bg-[#1c1d22]">
            {withData[hovered].label}: {fmtUsdCompact(withData[hovered].value)}
          </div>
        )}
      </div>
      <div className="mt-1 flex text-[10px] text-[#9a9ea8]">
        {withData.map((p, i) => (
          <div key={i} style={{ width: `${barWidth}%` }} className="truncate text-center">
            {p.label}
          </div>
        ))}
      </div>
    </div>
  );
}
