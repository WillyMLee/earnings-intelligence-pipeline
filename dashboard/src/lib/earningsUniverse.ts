import universe from "../data/neostellarEarningsUniverse.json";

export const normalizeTicker = (ticker: string) => ticker.trim().toUpperCase().replace(/\./g, "-");

export const SP500_TICKERS = new Set(universe.sp500.map(normalizeTicker));
export const NEOSTELLAR_ADDITIONS = new Set(universe.thematicAdditions.map(normalizeTicker));
export const TRACKED_TICKER_LIST = Array.from(new Set([...SP500_TICKERS, ...NEOSTELLAR_ADDITIONS])).sort();
export const TRACKED_TICKERS = new Set(TRACKED_TICKER_LIST);
export const TRACKED_UNIVERSE_AS_OF = universe.asOf;

export function isTrackedTicker(ticker: string) {
  return TRACKED_TICKERS.has(normalizeTicker(ticker));
}

export function normalizeAndFilterTracked<T extends { ticker: string }>(rows: T[]): T[] {
  return rows.flatMap((row) => {
    const ticker = normalizeTicker(row.ticker);
    return TRACKED_TICKERS.has(ticker) ? [{ ...row, ticker }] : [];
  });
}
