import { useEffect, useMemo, useState } from "react";
import { listByTicker, type PostEarningsSummary } from "../lib/convex";
import { fmtUsdCompact, fmtPct, fmtEps, fmtDate, beatMiss } from "../lib/format";
import { stripCitations, stripCitationsFromAll } from "../lib/citations";
import { CompanyLogo } from "../components/CompanyLogo";
import { Badge, ReactionBadge } from "../components/Badge";
import { StatCell } from "../components/StatCell";
import { StepList, ConnectedStepGroups } from "../components/StepList";
import { Tabs } from "../components/Tabs";
import { TrendChart } from "../components/TrendChart";
import { isReviewWarning } from "../lib/reporting";

const TAB_NAMES = ["Profile", "Financials", "Call highlights", "Reaction history", "Trends"];

export function CompanyProfile({ ticker, onBack }: { ticker: string; onBack: () => void }) {
  const [history, setHistory] = useState<PostEarningsSummary[] | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(TAB_NAMES[0]);
  const [selectedReportIdx, setSelectedReportIdx] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setHistory(null);
    setSelectedReportIdx(0);
    listByTicker(ticker, 20)
      .then((rows) => !cancelled && setHistory(rows))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (error) {
    return (
      <div className="p-8">
        <BackLink onBack={onBack} />
        <div className="mt-4 rounded-card border border-dashed border-rose-200 px-6 py-16 text-center text-rose-600 dark:border-rose-900 dark:text-rose-400">
          Couldn't load {ticker}: {error}
        </div>
      </div>
    );
  }
  if (!history) {
    return (
      <div className="p-8">
        <BackLink onBack={onBack} />
        <div className="mt-4 text-[14px] text-[#9a9ea8]">Loading…</div>
      </div>
    );
  }
  if (history.length === 0) {
    return (
      <div className="p-8">
        <BackLink onBack={onBack} />
        <div className="mt-4 rounded-card border border-dashed border-black/10 px-6 py-16 text-center text-[#9a9ea8] dark:border-white/10">
          No archived reports for {ticker} yet.
        </div>
      </div>
    );
  }

  const latest = history[0];
  const selectedReport = history[selectedReportIdx] ?? latest;

  return (
    <div className="p-6 sm:p-8">
      <BackLink onBack={onBack} />

      <header className="mt-4 flex flex-wrap items-start justify-between gap-6">
        <div className="flex items-center gap-4">
          <CompanyLogo ticker={latest.ticker} company={latest.company} size={56} />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[24px] font-extrabold text-[#15171c] dark:text-[#e7e8ea]">{latest.company}</h1>
              <span className="font-mono text-[14px] text-[#9a9ea8]">{latest.ticker}</span>
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              {latest.sector && <Badge>{latest.sector}</Badge>}
              <span className="text-[12px] text-[#9a9ea8]">
                {history.length} report{history.length === 1 ? "" : "s"} archived
              </span>
            </div>
          </div>
        </div>
        {/* Headline stats live here, once, at the top of the page -- every
            tab below reads against this instead of each re-deriving/
            re-showing its own copy of price/reaction. */}
        <div className="flex gap-5">
          <HeaderStat label="Price" value={latest.priceUsd != null ? `$${latest.priceUsd.toFixed(2)}` : "—"} />
          <HeaderStat label="Mkt cap" value={fmtUsdCompact(latest.marketCapUsd ?? null)} />
          <HeaderStat label="Last reaction" node={<ReactionBadge pct={latest.reactionPct} />} />
        </div>
      </header>

      <div className="mt-5">
        <Tabs tabs={TAB_NAMES} active={tab} onChange={setTab} />
      </div>

      <div className="mt-6">
        {tab === "Profile" && <ProfileTab latest={latest} />}
        {tab === "Financials" && <FinancialsTab latest={latest} history={history} />}
        {tab === "Call highlights" && (
          <CallHighlightsTab
            history={history}
            selectedIdx={selectedReportIdx}
            onSelect={setSelectedReportIdx}
            report={selectedReport}
          />
        )}
        {tab === "Reaction history" && <ReactionHistoryTab history={history} />}
        {tab === "Trends" && <TrendsTab history={history} />}
      </div>
    </div>
  );
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button onClick={onBack} className="text-[13px] font-medium text-[#8b8f99] hover:text-accent">
      ← All companies
    </button>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-black/[0.06] bg-white p-5 dark:border-white/[0.08] dark:bg-[#121317]">
      {children}
    </div>
  );
}

function HeaderStat({ label, value, node }: { label: string; value?: string; node?: React.ReactNode }) {
  return (
    <div className="text-right">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">{label}</div>
      <div className="mt-0.5">
        {node ?? <span className="text-[16px] font-bold text-[#15171c] dark:text-[#e7e8ea]">{value}</span>}
      </div>
    </div>
  );
}

function ProfileTab({ latest }: { latest: PostEarningsSummary }) {
  const links = latest.officialLinks ?? {};
  const linkEntries: [string, string][] = [
    ["Press release", links.press_release ?? ""],
    ["Investor deck", links.investor_deck ?? ""],
    ["Transcript", links.transcript ?? ""],
  ].filter(([, url]) => !!url) as [string, string][];
  const topHighlights = (latest.financialHighlights ?? []).filter((b) => !isReviewWarning(b.text)).slice(0, 3).map((b) => stripCitations(b.text).text);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[13px] text-[#5b5f6b] dark:text-[#9a9ea8]">
          <span><span className="text-[#8b8f99]">Quarter</span> · <span className="font-medium text-[#2b2e35] dark:text-[#dcdee2]">{latest.quarter}</span></span>
          <span><span className="text-[#8b8f99]">Reported</span> · <span className="font-medium text-[#2b2e35] dark:text-[#dcdee2]">{fmtDate(latest.reportDate)}, {latest.reportTime}</span></span>
        </div>
        <div className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">Latest report</div>
        <p className="mt-2 text-[14px] leading-relaxed text-[#2b2e35] dark:text-[#dcdee2]">
          {stripCitations(latest.intro).text || "No summary available."}
        </p>
        {linkEntries.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            {linkEntries.map(([label, url]) => (
              <a
                key={label}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="text-[12px] font-semibold text-accent hover:underline"
              >
                {label} ↗
              </a>
            ))}
          </div>
        )}
      </Card>

      {topHighlights.length > 0 && (
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">What mattered most</div>
            <span className="text-[11px] text-[#9a9ea8]">See Call highlights for the full brief →</span>
          </div>
          <StepList items={topHighlights} />
        </Card>
      )}
    </div>
  );
}

type FinRow = {
  label: string;
  sublabel?: string;
  value: (h: PostEarningsSummary) => string;
  verdict?: (h: PostEarningsSummary) => "beat" | "miss" | "inline" | null;
};

const FINANCIALS_ROWS: FinRow[] = [
  { label: "Revenue", value: (h) => fmtUsdCompact(h.revenueActualUsd) },
  { label: "Revenue YoY", value: (h) => fmtPct(h.revenueYoyPct) },
  {
    label: "Vs. consensus",
    value: (h) => (h.revenueConsensusUsd != null ? fmtUsdCompact(h.revenueConsensusUsd) : "Not tracked"),
    verdict: (h) => beatMiss(h.revenueActualUsd, h.revenueConsensusUsd),
  },
  { label: "EPS", value: (h) => fmtEps(h.epsActual) },
  {
    label: "EPS consensus",
    value: (h) => (h.epsConsensus != null ? fmtEps(h.epsConsensus) : "Not tracked"),
    verdict: (h) => beatMiss(h.epsActual, h.epsConsensus),
  },
  { label: "Net income", value: (h) => fmtUsdCompact(h.netIncomeActualUsd) },
  {
    label: "CapEx",
    value: (h) => fmtUsdCompact(h.capexActualUsd ?? null),
  },
  {
    label: "Cash & ST investments",
    value: (h) => fmtUsdCompact((h.cashAndEquivalentsUsd ?? 0) + (h.shortTermInvestmentsUsd ?? 0) || null),
  },
  {
    label: "Total debt",
    value: (h) => fmtUsdCompact((h.shortTermDebtUsd ?? 0) + (h.longTermDebtUsd ?? 0) || null),
  },
  { label: "Reaction", value: () => "" },
];

function FinancialsTab({ latest, history }: { latest: PostEarningsSummary; history: PostEarningsSummary[] }) {
  const revenueVerdict = beatMiss(latest.revenueActualUsd, latest.revenueConsensusUsd);
  const epsVerdict = beatMiss(latest.epsActual, latest.epsConsensus);
  // Most-recent-first, capped at 8 columns -- matches the familiar
  // Yahoo-Finance-style quarterly grid (metrics as rows, quarters as
  // columns) rather than one row per quarter, which reads badly once a
  // ticker has more than 3-4 archived reports.
  const cols = history.slice(0, 8);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <div className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">
          Latest quarter — {latest.quarter}
        </div>
        <div className="grid grid-cols-2 gap-y-4 sm:grid-cols-4">
          <StatCell label="Revenue" value={fmtUsdCompact(latest.revenueActualUsd)} sublabel={latest.revenueYoyPct != null ? `${fmtPct(latest.revenueYoyPct)} YoY` : undefined} />
          <StatCell label="Vs. Consensus" value={latest.revenueConsensusUsd != null ? fmtUsdCompact(latest.revenueConsensusUsd) : "Not tracked"} sublabel={revenueVerdict?.toUpperCase()} />
          <StatCell label="Net Income" value={fmtUsdCompact(latest.netIncomeActualUsd)} />
          <StatCell label="CapEx" value={fmtUsdCompact(latest.capexActualUsd)} sublabel={latest.capexGuidanceUpdatedUsd != null ? `FY guide ${fmtUsdCompact(latest.capexGuidanceUpdatedUsd)}` : undefined} />
          <StatCell label="EPS" value={fmtEps(latest.epsActual)} sublabel={latest.epsSurprisePct != null ? `${fmtPct(latest.epsSurprisePct)} surprise` : undefined} />
          <StatCell label="EPS Consensus" value={latest.epsConsensus != null ? fmtEps(latest.epsConsensus) : "Not tracked"} sublabel={epsVerdict?.toUpperCase()} />
          <StatCell label="Cash & ST Investments" value={fmtUsdCompact((latest.cashAndEquivalentsUsd ?? 0) + (latest.shortTermInvestmentsUsd ?? 0) || null)} />
          <StatCell label="Total Debt" value={fmtUsdCompact((latest.shortTermDebtUsd ?? 0) + (latest.longTermDebtUsd ?? 0) || null)} />
        </div>
        {(latest.consensusSource || latest.consensusCapturedAt) && (
          <div className="mt-4 border-t border-black/[0.05] pt-3 text-[11px] text-[#9a9ea8] dark:border-white/[0.06]">
            Consensus{latest.consensusCapturedAt ? ` captured ${fmtDate(latest.consensusCapturedAt.slice(0, 10))}` : ""}
            {latest.consensusSource ? ` · ${latest.consensusSource}` : ""}
          </div>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">
            Quarterly history
          </div>
          {history.length > cols.length && (
            <div className="text-[11px] text-[#9a9ea8]">Showing most recent {cols.length} of {history.length}</div>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-separate border-spacing-0 text-left text-[13px]">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-white pb-2 pr-4 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99] dark:bg-[#121317]" />
                {cols.map((h) => (
                  <th key={h._id} className="min-w-[92px] pb-2 pl-4 text-right text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">
                    <div className="text-[12px] font-bold normal-case text-[#15171c] dark:text-[#e7e8ea]">{h.quarter}</div>
                    <div className="font-normal normal-case text-[#9a9ea8]">{fmtDate(h.reportDate)}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FINANCIALS_ROWS.map((row) => (
                <tr key={row.label} className="border-t border-black/[0.05] dark:border-white/[0.06]">
                  <td className="sticky left-0 z-10 whitespace-nowrap bg-white py-2 pr-4 font-medium text-[#2b2e35] dark:bg-[#121317] dark:text-[#dcdee2]">
                    {row.label}
                  </td>
                  {cols.map((h) => {
                    if (row.label === "Reaction") {
                      return (
                        <td key={h._id} className="py-2 pl-4 text-right">
                          <ReactionBadge pct={h.reactionPct} />
                        </td>
                      );
                    }
                    const verdict = row.verdict?.(h);
                    return (
                      <td
                        key={h._id}
                        className={`py-2 pl-4 text-right tabular-nums ${
                          verdict === "beat"
                            ? "text-emerald-600 dark:text-emerald-400"
                            : verdict === "miss"
                              ? "text-rose-600 dark:text-rose-400"
                              : "text-[#2b2e35] dark:text-[#dcdee2]"
                        }`}
                      >
                        {row.value(h)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function CallHighlightsTab({
  history,
  selectedIdx,
  onSelect,
  report,
}: {
  history: PostEarningsSummary[];
  selectedIdx: number;
  onSelect: (idx: number) => void;
  report: PostEarningsSummary;
}) {
  const intro = stripCitations(report.intro);
  const rawHighlightBullets = (report.financialHighlights ?? []).map((b) => stripCitations(b.text).text);
  const warningBullets = rawHighlightBullets.filter(isReviewWarning);
  const highlightBullets = rawHighlightBullets.filter((text) => !isReviewWarning(text));
  const highlightUrls = stripCitationsFromAll((report.financialHighlights ?? []).map((b) => b.text)).urls;
  const sectionUrls = useMemo(
    () =>
      (report.sections ?? []).flatMap((s) => stripCitationsFromAll(s.bullets.map((b) => b.text)).urls),
    [report]
  );
  const allSources = Array.from(new Set([...intro.urls, ...highlightUrls, ...sectionUrls]));

  const hasDetail =
    intro.text || highlightBullets.length > 0 || (report.sections?.length ?? 0) > 0 || (report.qaHighlights?.length ?? 0) > 0;

  // One continuous connected flow -- "Financial highlights" plus every
  // themed section -- instead of a separate boxed card (and a numbering
  // restart) per section.
  const stepGroups = [
    ...(highlightBullets.length > 0 ? [{ heading: "Financial highlights", items: highlightBullets }] : []),
    ...(report.sections ?? []).map((section) => ({
      heading: section.heading,
      items: section.bullets.map((b) => stripCitations(b.text).text).filter((text) => !isReviewWarning(text)),
    })),
  ];

  return (
    <div className="flex flex-col gap-6">
      {history.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {history.map((h, i) => (
            <button
              key={h._id}
              onClick={() => onSelect(i)}
              className={`rounded-full border px-3 py-1 text-[12px] font-medium ${
                selectedIdx === i
                  ? "border-accent bg-accent-soft text-accent dark:bg-accent/20"
                  : "border-black/[0.08] text-[#5b5f6b] dark:border-white/[0.1] dark:text-[#9a9ea8]"
              }`}
            >
              {h.quarter}
            </button>
          ))}
        </div>
      )}

      {!hasDetail && (
        <Card>
          <div className="text-[13px] text-[#9a9ea8]">
            No detailed brief archived for this report (only the compact summary is available).
          </div>
        </Card>
      )}

      {hasDetail && (
        <>
          {intro.text && (
            <Card>
              <p className="text-[14px] leading-relaxed text-[#2b2e35] dark:text-[#dcdee2]">{intro.text}</p>
            </Card>
          )}

          {warningBullets.length > 0 && (
            <div className="rounded-card border border-amber-300/50 bg-amber-50 px-4 py-3 text-[12px] leading-relaxed text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/[0.08] dark:text-amber-200">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-700 dark:text-amber-300">Verification note</div>
              {warningBullets.map((warning, index) => <div key={index}>{warning.replace(/^\s*(note|warning|caveat)\s*:\s*/i, "")}</div>)}
            </div>
          )}

          {(report.qaHighlights?.length ?? 0) > 0 && (
            <Card>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">Q&amp;A highlights</div>
                <div className="flex items-center gap-3 text-[11px] text-[#9a9ea8]">
                  <span>{report.qaHighlights!.length} exchanges</span>
                  {report.officialLinks?.transcript && <a href={report.officialLinks.transcript} target="_blank" rel="noreferrer" className="text-accent hover:underline">Transcript</a>}
                </div>
              </div>
              <div className="flex flex-col gap-4">
                {report.qaHighlights!.map((qa, i) => (
                  <div key={i} className={i > 0 ? "border-t border-black/[0.06] pt-4 dark:border-white/[0.06]" : ""}>
                    <div className="flex gap-2 text-[13px] leading-snug">
                      <span className="shrink-0 font-bold text-accent">Q</span>
                      <span className="font-medium text-[#15171c] dark:text-[#e7e8ea]">{qa.analystQuestion}</span>
                    </div>
                    <div className="mt-1.5 flex gap-2 text-[13px] leading-snug">
                      <span className="shrink-0 font-bold text-[#8b8f99]">A</span>
                      <span className="text-[#2b2e35] dark:text-[#dcdee2]">{qa.answerSummary}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {stepGroups.length > 0 && (
            <Card><ConnectedStepGroups groups={stepGroups} /></Card>
          )}

          {allSources.length > 0 && (
            <details className="rounded-card border border-black/[0.06] bg-white px-5 py-4 dark:border-white/[0.08] dark:bg-[#121317]">
              <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.1em] text-[#8b8f99]">Sources · {allSources.length}</summary>
              <div className="mt-3 flex flex-col gap-1 border-t border-black/[0.05] pt-3 dark:border-white/[0.06]">
                {allSources.map((url) => <a key={url} href={url} target="_blank" rel="noreferrer" className="truncate text-[12px] text-accent hover:underline">{url}</a>)}
              </div>
            </details>
          )}
        </>
      )}
    </div>
  );
}

function ReactionHistoryTab({ history }: { history: PostEarningsSummary[] }) {
  return (
    <Card>
      <div className="flex flex-col divide-y divide-black/[0.05] dark:divide-white/[0.06]">
        {history.map((h) => (
          <div key={h._id} className="flex items-center justify-between gap-4 py-3">
            <div>
              <div className="text-[13px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">
                {h.quarter} · {fmtDate(h.reportDate)}
              </div>
              {h.reactionLine && <div className="mt-0.5 text-[12px] text-[#9a9ea8]">{h.reactionLine}</div>}
            </div>
            <ReactionBadge pct={h.reactionPct} />
          </div>
        ))}
      </div>
    </Card>
  );
}

function TrendsTab({ history }: { history: PostEarningsSummary[] }) {
  // Oldest -> newest for left-to-right chronological reading.
  const chrono = history.slice().reverse();
  const points = (selector: (h: PostEarningsSummary) => number | null) =>
    chrono.map((h) => ({ label: h.quarter, value: selector(h) }));

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
      <Card>
        <TrendChart title="Revenue" points={points((h) => h.revenueActualUsd)} />
      </Card>
      <Card>
        <TrendChart title="Net Income" points={points((h) => h.netIncomeActualUsd)} />
      </Card>
      <Card>
        <TrendChart
          title="Cash & Short-Term Investments"
          points={points((h) =>
            h.cashAndEquivalentsUsd != null || h.shortTermInvestmentsUsd != null
              ? (h.cashAndEquivalentsUsd ?? 0) + (h.shortTermInvestmentsUsd ?? 0)
              : null
          )}
        />
      </Card>
      <Card>
        <TrendChart title="Long-Term Debt" points={points((h) => h.longTermDebtUsd ?? null)} />
      </Card>
      <Card>
        <TrendChart title="Short-Term Debt" points={points((h) => h.shortTermDebtUsd ?? null)} />
      </Card>
    </div>
  );
}
