import type { PostEarningsSummary } from "../lib/convex";
import { fmtUsdCompact, fmtPct, fmtEps, relativeDay, beatMiss } from "../lib/format";
import { Badge, ReactionBadge } from "./Badge";
import { StatCell } from "./StatCell";
import { StepList } from "./StepList";
import { CompanyLogo } from "./CompanyLogo";

export function EarningsCard({
  summary,
  onOpenCompany,
}: {
  summary: PostEarningsSummary;
  onOpenCompany: (ticker: string) => void;
}) {
  const revenueVerdict = beatMiss(summary.revenueActualUsd, summary.revenueConsensusUsd);
  const epsVerdict = beatMiss(summary.epsActual, summary.epsConsensus);

  return (
    <article className="rounded-card border border-black/[0.06] bg-white p-5 shadow-[0_1px_2px_rgba(15,15,20,0.04)] dark:border-white/[0.08] dark:bg-[#121317]">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <button
          onClick={() => onOpenCompany(summary.ticker)}
          className="flex items-center gap-3 text-left"
        >
          <CompanyLogo ticker={summary.ticker} company={summary.company} size={40} />
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-[15px] font-semibold text-[#15171c] hover:underline dark:text-[#e7e8ea]">
                {summary.company}
              </h3>
              <span className="font-mono text-[12px] text-[#9a9ea8]">{summary.ticker}</span>
            </div>
            <div className="mt-0.5 text-[12px] text-[#9a9ea8]">
              {summary.quarter} · {relativeDay(summary.reportDate)} · {summary.reportTime}
            </div>
          </div>
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {summary.sector && <Badge>{summary.sector}</Badge>}
          <ReactionBadge pct={summary.reactionPct} />
        </div>
      </header>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-black/[0.06] py-4 dark:border-white/[0.08] sm:grid-cols-4">
        <StatCell
          label="Revenue"
          value={fmtUsdCompact(summary.revenueActualUsd)}
          sublabel={summary.revenueYoyPct !== null ? `${fmtPct(summary.revenueYoyPct)} YoY` : undefined}
        />
        <StatCell
          label="Vs. Consensus"
          value={summary.revenueConsensusUsd !== null ? fmtUsdCompact(summary.revenueConsensusUsd) : "Not tracked"}
          sublabel={revenueVerdict ? revenueVerdict.toUpperCase() : undefined}
        />
        <StatCell
          label="EPS"
          value={fmtEps(summary.epsActual)}
          sublabel={summary.epsSurprisePct !== null ? `${fmtPct(summary.epsSurprisePct)} surprise` : undefined}
        />
        <StatCell
          label="EPS Consensus"
          value={summary.epsConsensus !== null ? fmtEps(summary.epsConsensus) : "Not tracked"}
          sublabel={epsVerdict ? epsVerdict.toUpperCase() : undefined}
        />
      </div>

      {summary.keyMetrics.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99] dark:text-[#7d818c]">
            What mattered
          </div>
          <StepList items={summary.keyMetrics.slice(0, 3)} />
          {summary.keyMetrics.length > 3 && (
            <div className="mt-2 pl-4 text-[11px] text-[#9a9ea8]">+{summary.keyMetrics.length - 3} more points in the full profile</div>
          )}
        </div>
      )}

      <button
        onClick={() => onOpenCompany(summary.ticker)}
        className="mt-4 text-[12px] font-semibold text-accent hover:underline"
      >
        View full profile →
      </button>
    </article>
  );
}
