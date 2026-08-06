import { useEffect, useMemo, useState } from "react";
import { listByTicker, type PostEarningsSummary } from "../lib/convex";
import { fmtUsdCompact, fmtPct, fmtEps, fmtDate, beatMiss } from "../lib/format";
import { stripCitations, stripCitationsFromAll } from "../lib/citations";
import { CompanyLogo } from "../components/CompanyLogo";
import { Badge, ReactionBadge } from "../components/Badge";
import { StatCell } from "../components/StatCell";
import { StepList } from "../components/StepList";
import { Tabs } from "../components/Tabs";
import { TrendChart } from "../components/TrendChart";

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

      <header className="mt-4 flex flex-wrap items-center gap-4">
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
      </header>

      <div className="mt-6">
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

function ProfileTab({ latest }: { latest: PostEarningsSummary }) {
  const links = latest.officialLinks ?? {};
  const linkEntries: [string, string][] = [
    ["Press release", links.press_release ?? ""],
    ["Investor deck", links.investor_deck ?? ""],
    ["Transcript", links.transcript ?? ""],
  ].filter(([, url]) => !!url) as [string, string][];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Card>
        <StatCell label="Price" value={latest.priceUsd != null ? `$${latest.priceUsd.toFixed(2)}` : "—"} sublabel={`As of ${fmtDate(latest.reportDate)}`} />
      </Card>
      <Card>
        <StatCell label="Market Cap" value={fmtUsdCompact(latest.marketCapUsd)} sublabel={`As of ${fmtDate(latest.reportDate)}`} />
      </Card>
      <Card>
        <StatCell label="Last Reaction" value={latest.reactionPct != null ? fmtPct(latest.reactionPct) : "—"} sublabel={latest.reportTime} />
      </Card>
      <div className="sm:col-span-3">
        <Card>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">Latest report</div>
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
      </div>
    </div>
  );
}

function FinancialsTab({ latest, history }: { latest: PostEarningsSummary; history: PostEarningsSummary[] }) {
  const revenueVerdict = beatMiss(latest.revenueActualUsd, latest.revenueConsensusUsd);
  const epsVerdict = beatMiss(latest.epsActual, latest.epsConsensus);

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
      </Card>

      <Card>
        <div className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">History</div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-[#8b8f99]">
                <th className="pb-2 pr-4 font-semibold">Quarter</th>
                <th className="pb-2 pr-4 font-semibold">Reported</th>
                <th className="pb-2 pr-4 font-semibold">Revenue</th>
                <th className="pb-2 pr-4 font-semibold">EPS</th>
                <th className="pb-2 font-semibold">Reaction</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h._id} className="border-t border-black/[0.05] dark:border-white/[0.06]">
                  <td className="py-2 pr-4 font-medium text-[#15171c] dark:text-[#e7e8ea]">{h.quarter}</td>
                  <td className="py-2 pr-4 text-[#5b5f6b] dark:text-[#9a9ea8]">{fmtDate(h.reportDate)}</td>
                  <td className="py-2 pr-4">{fmtUsdCompact(h.revenueActualUsd)}</td>
                  <td className="py-2 pr-4">{fmtEps(h.epsActual)}</td>
                  <td className="py-2">
                    <ReactionBadge pct={h.reactionPct} />
                  </td>
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
  const highlightBullets = (report.financialHighlights ?? []).map((b) => stripCitations(b.text).text);
  const highlightUrls = stripCitationsFromAll((report.financialHighlights ?? []).map((b) => b.text)).urls;
  const sectionUrls = useMemo(
    () =>
      (report.sections ?? []).flatMap((s) => stripCitationsFromAll(s.bullets.map((b) => b.text)).urls),
    [report]
  );
  const allSources = Array.from(new Set([...intro.urls, ...highlightUrls, ...sectionUrls]));

  const hasDetail = intro.text || highlightBullets.length > 0 || (report.sections?.length ?? 0) > 0;

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

          {highlightBullets.length > 0 && (
            <Card>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">
                Financial highlights
              </div>
              <StepList items={highlightBullets} />
            </Card>
          )}

          {(report.sections ?? []).map((section, i) => {
            const bulletTexts = section.bullets.map((b) => stripCitations(b.text).text);
            return (
              <Card key={i}>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">
                  {section.heading}
                </div>
                <StepList items={bulletTexts} />
              </Card>
            );
          })}

          {allSources.length > 0 && (
            <Card>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99]">Sources</div>
              <div className="flex flex-col gap-1">
                {allSources.map((url) => (
                  <a key={url} href={url} target="_blank" rel="noreferrer" className="truncate text-[12px] text-accent hover:underline">
                    {url}
                  </a>
                ))}
              </div>
            </Card>
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
