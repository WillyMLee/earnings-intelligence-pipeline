import { displayCompanyName } from "./companyNames";

// Thin, dependency-free client for Convex's HTTP query API -- avoids
// pulling in the full convex-react SDK for what is, from this dashboard's
// point of view, a handful of read-only queries. Swap CONVEX_URL for your
// own deployment if you're porting this (see the root README's porting
// guide) -- the schema/query shapes are documented in convex/schema.js.
// The production Convex URL is a public API endpoint, not a credential.
// Keep an explicit fallback so Cloudflare's clean Git builds do not silently
// compile an empty URL when local-only .env files are unavailable.
const CONVEX_URL =
  (import.meta.env.VITE_CONVEX_URL as string | undefined) ||
  "https://honorable-goldfish-309.convex.cloud";

export type Bullet = { text: string; children?: string[] };
export type Section = { heading: string; bullets: Bullet[] };
export type OfficialLinks = { press_release?: string; investor_deck?: string; transcript?: string };
export type QaHighlight = { analystQuestion: string; answerSummary: string };

export type PostEarningsSummary = {
  _id: string;
  ticker: string;
  company: string;
  quarter: string;
  reportDate: string;
  reportTime: string;
  reactionPct: number | null;
  reactionLine: string | null;
  keyMetrics: string[];
  sector?: string;
  revenueActualUsd: number | null;
  revenueConsensusUsd: number | null;
  revenueYoyPct: number | null;
  netIncomeActualUsd: number | null;
  epsActual: number | null;
  epsConsensus: number | null;
  epsSurprisePct: number | null;
  capexActualUsd?: number | null;
  capexGuidancePriorUsd?: number | null;
  capexGuidanceUpdatedUsd?: number | null;
  cashAndEquivalentsUsd?: number | null;
  shortTermInvestmentsUsd?: number | null;
  shortTermDebtUsd?: number | null;
  longTermDebtUsd?: number | null;
  totalDebtUsd?: number | null;
  priceUsd?: number | null;
  marketCapUsd?: number | null;
  intro?: string | null;
  financialHighlights?: Bullet[] | null;
  sections?: Section[] | null;
  officialLinks?: OfficialLinks | null;
  qaHighlights?: QaHighlight[] | null;
  consensusSource?: string | null;
  consensusCapturedAt?: string | null;
  updatedAt: string;
};

// Narrow, source-verified repair for a row archived before the report-day
// publication gate existed. Remove this override after the same correction
// is persisted in Convex. Keeping it keyed by ticker + report date prevents
// it from leaking into future CoreWeave quarters.
const VERIFIED_SUMMARY_CORRECTIONS: Record<string, Partial<PostEarningsSummary>> = {
  "CRWV:2026-08-11": {
    revenueActualUsd: 2_575_000_000,
    revenueConsensusUsd: 2_560_000_000,
    revenueYoyPct: 112.3,
    netIncomeActualUsd: -626_000_000,
    epsActual: -1.14,
    epsConsensus: null,
    epsSurprisePct: null,
    capexActualUsd: 9_352_000_000,
    cashAndEquivalentsUsd: 5_524_000_000,
    shortTermInvestmentsUsd: 0,
    shortTermDebtUsd: null,
    longTermDebtUsd: null,
    totalDebtUsd: 35_100_000_000,
    consensusSource: "LSEG (pre-print)",
    intro:
      "CoreWeave reported Q2 2026 revenue of $2.575B, up approximately 112.3% year over year and 0.6% above the $2.560B LSEG consensus. GAAP net loss was $(626)M, or $(1.14) per diluted share; adjusted net loss was $(567)M. Revenue backlog reached $104.2B, while Q2 capital expenditures were $9.352B and quarterly net interest expense was $640M.",
    financialHighlights: [
      { text: "Revenue: $2.575B versus $2.560B LSEG consensus, a 0.6% beat; approximately 112.3% year over year.", children: [] },
      { text: "GAAP net loss: $(626)M, or $(1.14) per diluted share; adjusted net loss was $(567)M.", children: [] },
      { text: "Adjusted EBITDA: $1.510B, with a 59% adjusted EBITDA margin.", children: [] },
      { text: "Revenue backlog: $104.2B, excluding more than $25B of early-Q3 customer commitments.", children: [] },
      { text: "Capital expenditures: $9.352B in Q2 and $16.139B in the first half.", children: [] },
      { text: "Cash and cash equivalents were $5.524B; total debt was approximately $35.1B, excluding lease liabilities.", children: [] },
    ],
    keyMetrics: [
      "Revenue: $2.575B versus $2.560B LSEG consensus, a 0.6% beat; approximately 112.3% year over year.",
      "GAAP net loss: $(626)M, or $(1.14) per diluted share.",
      "Adjusted EBITDA: $1.510B, with a 59% margin.",
      "Revenue backlog: $104.2B, excluding more than $25B of early-Q3 commitments.",
      "Capital expenditures: $9.352B in Q2 and $16.139B in the first half.",
      "Active power: 1.5 GW; contracted power: approximately 3.7 GW.",
    ],
    officialLinks: {
      press_release: "https://www.sec.gov/Archives/edgar/data/1769628/000176962826000362/coreweave2q26earningspress.htm",
      investor_deck: "https://s205.q4cdn.com/133937190/files/doc_financials/2026/q2/CoreWeave-Q2-26-Earnings-Presentation.pdf",
    },
  },
};

function normalizeSummary(row: PostEarningsSummary): PostEarningsSummary {
  const correction = VERIFIED_SUMMARY_CORRECTIONS[`${row.ticker}:${row.reportDate}`] ?? {};
  return {
    ...row,
    ...correction,
    company: displayCompanyName(row.ticker, row.company),
  };
}

export type CompanyListing = {
  ticker: string;
  company: string;
  sector: string | null;
  reportDate: string;
};

export type CalendarEvent = {
  ticker: string;
  company: string;
  reportDate: string;
  reportTime: string;
  sector?: string;
  epsEstimate?: number | null;
  revenueEstimateUsd?: number | null;
  dateConfidence?: "confirmed" | "inferred";
  updatedAt?: string;
};

export type ReportingProgress = {
  start: string;
  end: string;
  total: number;
  reported: number;
  percent: number;
  scheduled: CalendarEvent[];
};

async function convexQuery<T>(path: string, args: Record<string, unknown>): Promise<T> {
  if (!CONVEX_URL) {
    throw new Error(
      "VITE_CONVEX_URL is not set. Copy .env.example to .env.local and point it at your Convex deployment."
    );
  }
  const response = await fetch(`${CONVEX_URL.replace(/\/$/, "")}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, args, format: "json" }),
  });
  if (!response.ok) {
    throw new Error(`Convex query ${path} failed: HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (payload.status !== "success") {
    throw new Error(`Convex query ${path} failed: ${payload.errorMessage ?? "unknown error"}`);
  }
  return payload.value as T;
}

export function listRecentEarnings(limit = 50, sector?: string) {
  return convexQuery<PostEarningsSummary[]>("postEarningsSummaries:listRecent", {
    limit,
    ...(sector ? { sector } : {}),
  }).then((rows) => rows.map(normalizeSummary));
}

export function listSectors() {
  return convexQuery<string[]>("postEarningsSummaries:listSectors", {});
}

export function listCompanies() {
  return convexQuery<CompanyListing[]>("postEarningsSummaries:listCompanies", {}).then((rows) =>
    rows.map((row) => ({ ...row, company: displayCompanyName(row.ticker, row.company) }))
  );
}

export function listByTicker(ticker: string, limit = 20) {
  return convexQuery<PostEarningsSummary[]>("postEarningsSummaries:listByTicker", { ticker, limit }).then((rows) =>
    rows.map(normalizeSummary)
  );
}

export function listCalendarEvents(start: string, end: string, tickers?: string[]) {
  return convexQuery<CalendarEvent[]>("earningsCalendar:listWindow", {
    start,
    end,
    ...(tickers ? { tickers } : {}),
  }).then((rows) => rows.map((row) => ({ ...row, company: displayCompanyName(row.ticker, row.company) })));
}

export function getReportingProgress(start: string, end: string, tickers?: string[]) {
  return convexQuery<ReportingProgress>("earningsCalendar:reportingProgress", {
    start,
    end,
    ...(tickers ? { tickers } : {}),
  });
}
