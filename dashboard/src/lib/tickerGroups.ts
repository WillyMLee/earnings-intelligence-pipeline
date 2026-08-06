// Mirrors MAG7_TICKERS / TOP100_TICKERS in earnings_workflows_common/coverage.py --
// keep in sync if that list changes. Purely a client-side filter tag, not
// something that needs a Convex round-trip.
export const MAG7_TICKERS = new Set([
  "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
]);

export const TOP100_TICKERS = new Set([
  "NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "TSM", "AVGO", "META", "SPCX", "TSLA",
  "BRK-B", "LLY", "MU", "JPM", "WMT", "AMD", "V", "ASML", "XOM", "JNJ",
  "INTC", "MA", "CSCO", "BAC", "ABBV", "AMAT", "COST", "ORCL", "CAT", "GE",
  "LRCX", "PLTR", "UNH", "KO", "CVX", "HD", "MS", "PG", "MRK", "GS",
  "NFLX", "DELL", "RTX", "PANW", "PM", "ARM", "WFC", "GEV", "TXN", "KLAC",
  "ANET", "C", "AXP", "LIN", "IBM", "AMGN", "TMO", "CRWD", "APH", "SNDK",
  "MCD", "VZ", "BA", "PEP", "SCHW", "STX", "TMUS", "MRVL", "ABT", "ADI",
  "NEE", "WDC", "TJX", "BLK", "DIS", "UNP", "ETN", "WELL", "QCOM", "DE",
  "GILD", "T", "CRM", "BKNG", "PFE", "DHR", "COP", "APP", "UBER", "COF",
  "CB", "GLW", "LMT", "ISRG", "PLD", "BTI", "BMY", "SYK", "CVS", "PH",
]);

export type TickerFilter = "all" | "mag7" | "top100";

export const TICKER_FILTER_LABEL: Record<TickerFilter, string> = {
  all: "All companies",
  mag7: "Mag 7",
  top100: "Top 100",
};
