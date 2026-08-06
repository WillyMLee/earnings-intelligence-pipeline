// Thin, dependency-free client for Convex's HTTP query API -- avoids
// pulling in the full convex-react SDK for what is, from this dashboard's
// point of view, a handful of read-only queries. Swap CONVEX_URL for your
// own deployment if you're porting this (see the root README's porting
// guide) -- the schema/query shapes are documented in convex/schema.js.
const CONVEX_URL = import.meta.env.VITE_CONVEX_URL as string;

export type Bullet = { text: string; children?: string[] };
export type Section = { heading: string; bullets: Bullet[] };
export type OfficialLinks = { press_release?: string; investor_deck?: string; transcript?: string };

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
  priceUsd?: number | null;
  marketCapUsd?: number | null;
  intro?: string | null;
  financialHighlights?: Bullet[] | null;
  sections?: Section[] | null;
  officialLinks?: OfficialLinks | null;
  updatedAt: string;
};

export type CompanyListing = {
  ticker: string;
  company: string;
  sector: string | null;
  reportDate: string;
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
  });
}

export function listSectors() {
  return convexQuery<string[]>("postEarningsSummaries:listSectors", {});
}

export function listCompanies() {
  return convexQuery<CompanyListing[]>("postEarningsSummaries:listCompanies", {});
}

export function listByTicker(ticker: string, limit = 20) {
  return convexQuery<PostEarningsSummary[]>("postEarningsSummaries:listByTicker", { ticker, limit });
}
